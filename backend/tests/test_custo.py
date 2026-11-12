"""Redução de custo de IA sem perder auditoria: medição, resposta enxuta, detecção local de fala,
teto diário e a regra "sem segurança, não acusa o operador"."""
from datetime import datetime

import numpy as np
import pytest
from sqlalchemy import select

from app.config import settings
from app.database import SessionLocal
from app.models import Call, IaUso
from app.services import ai_qualifier, audio_analyzer, custos, pipeline

from helpers import IAFalsa as _IAFalsa, fala as _fala, silencio as _silencio, wav as _wav  # noqa: E402

SR = 8000


# --------------------------------------------------------------------------- detecção local de fala
def test_vad_silencio_nao_tem_fala(tmp_path):
    m = audio_analyzer.analyze(_wav(tmp_path / "s.wav", [_silencio(8)]))
    assert m["vad"] is True
    assert m["fala_segundos"] < 0.3
    assert 7.5 < m["duracao_segundos"] < 8.5


def test_vad_mede_o_trecho_com_voz(tmp_path):
    m = audio_analyzer.analyze(_wav(tmp_path / "f.wav", [_fala(10, 2, 3)]))
    assert 2.5 < m["fala_segundos"] < 3.5


def test_vad_estereo_mede_cada_lado(tmp_path):
    m = audio_analyzer.analyze(_wav(tmp_path / "st.wav", [_fala(10, 1, 4), _silencio(10)]))
    assert m["canais"] == 2
    a, b = m["fala_por_canal"]
    assert 3.5 < a < 4.5 and b < 0.3


def test_vad_ruido_constante_e_tratado_como_fala(tmp_path):
    """Na dúvida, vai para a IA: ruído forte contínuo não pode ser descartado como 'mudo'."""
    ruido = np.random.default_rng(3).normal(0, 0.1, 6 * SR)
    m = audio_analyzer.analyze(_wav(tmp_path / "r.wav", [ruido]))
    assert m["fala_segundos"] > 5


def test_arquivo_ilegivel_nao_quebra(tmp_path):
    p = tmp_path / "x.mp3"
    p.write_bytes(b"\x00" * 64)
    m = audio_analyzer.analyze(str(p))
    assert m["vad"] is False


# --------------------------------------------------------------------------- mudo total sem IA
def test_ligacao_sem_fala_e_resolvida_localmente_sem_gastar(tmp_path, monkeypatch):
    ia = _IAFalsa(monkeypatch)
    with SessionLocal() as db:
        c = Call(id_ligacao=410001, caminho_audio=_wav(tmp_path / "m.wav", [_silencio(6)]), status="pending")
        db.add(c)
        db.commit()
        pipeline.qualificar_call(db, c)
        assert (c.status, c.categoria, c.subcategoria, c.motor) == ("done", "LIGACAO_MUDA", "MUDO_TOTAL", "local")
        assert ia.transcricoes == 0 and ia.classificacoes == 0
        assert (c.custo_usd or 0) == 0


def test_mudo_total_local_funciona_sem_chave_de_ia(tmp_path):
    with SessionLocal() as db:
        c = Call(id_ligacao=410002, caminho_audio=_wav(tmp_path / "m2.wav", [_silencio(5)]), status="pending")
        db.add(c)
        db.commit()
        pipeline.qualificar_call(db, c)
        assert c.status == "done" and c.motor == "local"


def test_sem_vad_confiavel_a_ligacao_segue_para_a_ia(tmp_path, monkeypatch):
    ia = _IAFalsa(monkeypatch)
    p = tmp_path / "ruim.mp3"
    p.write_bytes(b"\x00" * 64)
    with SessionLocal() as db:
        c = Call(id_ligacao=410003, caminho_audio=str(p), status="pending")
        db.add(c)
        db.commit()
        pipeline.qualificar_call(db, c)
        assert ia.transcricoes == 1 and c.motor == "openai"


# --------------------------------------------------------------------------- medição de custo
def test_custo_da_ligacao_e_registrado(tmp_path, monkeypatch):
    _IAFalsa(monkeypatch, tokens=(1200, 100))
    monkeypatch.setattr(settings, "cortar_silencio", False)
    monkeypatch.setattr(settings, "openai_whisper_model", "gpt-4o-mini-transcribe")
    monkeypatch.setattr(settings, "openai_model", "gpt-4o-mini")
    with SessionLocal() as db:
        c = Call(id_ligacao=420001, caminho_audio=_wav(tmp_path / "c.wav", [_fala(60, 1, 30)]), status="pending")
        db.add(c)
        db.commit()
        pipeline.qualificar_call(db, c)
        usos = db.scalars(select(IaUso).where(IaUso.call_id == c.id)).all()
        assert {u.tipo for u in usos} == {"transcricao", "classificacao"}
        esperado = 1.0 * 0.003 + 1200 * 0.15e-6 + 100 * 0.60e-6  # 60 s de áudio + tokens
        assert c.custo_usd == pytest.approx(esperado, rel=0.02)
        assert sum(u.custo_usd for u in usos) == pytest.approx(c.custo_usd)


def test_transcricao_paga_e_contada_mesmo_se_a_classificacao_falhar(tmp_path, monkeypatch):
    _IAFalsa(monkeypatch, falha_classificacao=True)
    with SessionLocal() as db:
        c = Call(id_ligacao=420002, caminho_audio=_wav(tmp_path / "c2.wav", [_fala(30, 1, 20)]), status="pending")
        db.add(c)
        db.commit()
        pipeline.qualificar_call(db, c)
        assert c.status == "error" and c.custo_usd > 0
        tipos = [u.tipo for u in db.scalars(select(IaUso).where(IaUso.call_id == c.id))]
        assert tipos == ["transcricao"]


def test_reanalise_reaproveita_a_transcricao(tmp_path, monkeypatch):
    ia = _IAFalsa(monkeypatch)
    with SessionLocal() as db:
        c = Call(id_ligacao=420003, caminho_audio=_wav(tmp_path / "c3.wav", [_fala(20, 1, 10)]), status="pending")
        db.add(c)
        db.commit()
        pipeline.qualificar_call(db, c)
        pipeline.qualificar_call(db, c, force=True)
        assert ia.transcricoes == 1 and ia.classificacoes == 2


def test_precos_por_modelo_e_sobrescrita(monkeypatch):
    assert custos.preco_transcricao("whisper-1") == 0.006
    assert custos.preco_transcricao("gpt-4o-mini-transcribe") == 0.003
    assert custos.preco_chat("gpt-4o-mini") == (0.15, 0.60)
    assert custos.preco_transcricao("modelo-desconhecido") is None
    monkeypatch.setattr(settings, "preco_transcricao_minuto", 0.001)
    assert custos.preco_transcricao("modelo-desconhecido") == 0.001


# --------------------------------------------------------------------------- resposta enxuta
def test_resposta_da_ia_nao_repete_a_transcricao():
    from openai.lib._parsing import type_to_response_format_param

    props = type_to_response_format_param(ai_qualifier.RespostaIA)["json_schema"]["schema"]["properties"]
    assert "categoria" in props and "evidencia" in props
    assert "transcricao" not in props and "turnos" not in props
    diar = type_to_response_format_param(ai_qualifier.RespostaIADiarizada)["json_schema"]["schema"]["properties"]
    assert "turnos" in diar and "transcricao" not in diar


def test_ia_pode_responder_indeterminado():
    prompt = ai_qualifier.montar_prompt()
    assert "INDETERMINADO" in prompt and "AUDIO_INAUDIVEL" in prompt


# --------------------------------------------------------------------------- teto diário
def test_teto_diario_segura_a_ligacao_sem_chamar_a_ia(tmp_path, monkeypatch):
    ia = _IAFalsa(monkeypatch)
    with SessionLocal() as db:
        outra = Call(id_ligacao=430001, status="done")
        db.add(outra)
        db.commit()
        custos.registrar(db, outra, "transcricao", "whisper-1", audio_segundos=600)  # US$ 0,06 hoje
        db.commit()
        monkeypatch.setattr(settings, "ia_teto_diario_usd", 0.01)
        c = Call(id_ligacao=430002, caminho_audio=_wav(tmp_path / "t.wav", [_fala(20, 1, 10)]), status="pending")
        db.add(c)
        db.commit()
        pipeline.qualificar_call(db, c)
        assert c.status == "awaiting_ai" and "teto" in (c.erro or "").lower()
        assert ia.transcricoes == 0
        monkeypatch.setattr(settings, "ia_teto_diario_usd", 0)  # sem teto: processa
        pipeline.qualificar_call(db, c)
        assert c.status == "done"


# --------------------------------------------------------------------------- sem segurança, não acusa
def _call(**kw):
    return Call(tabulacao_operador="CLIENTE NÃO TEM INTERESSE", status="done", **kw)


def test_indeterminado_nao_vira_divergencia_e_vai_para_revisao():
    c = _call(categoria="INDETERMINADO", subcategoria="AUDIO_INAUDIVEL", confianca=0.3)
    pipeline.calcular_divergencia(c)
    assert c.divergencia_tabulacao is False
    assert c.precisa_revisao is True and c.revisao_motivo


def test_divergencia_com_confianca_baixa_vai_para_revisao_em_vez_de_acusar():
    c = _call(categoria="EM_NEGOCIACAO", confianca=0.45)
    pipeline.calcular_divergencia(c)
    assert c.divergencia_tabulacao is False and c.precisa_revisao is True
    assert "45%" in c.revisao_motivo


def test_divergencia_com_confianca_alta_continua_valendo():
    c = _call(categoria="EM_NEGOCIACAO", confianca=0.9)
    pipeline.calcular_divergencia(c)
    assert c.divergencia_tabulacao is True and not c.precisa_revisao


def test_concordancia_com_confianca_baixa_nao_gera_revisao():
    c = _call(categoria="SEM_INTERESSE", confianca=0.4)
    pipeline.calcular_divergencia(c)
    assert c.divergencia_tabulacao is False and not c.precisa_revisao


# --------------------------------------------------------------------------- "tabulou muda, mas tem conversa"
def test_muda_com_fala_dos_dois_lados_entra_na_revisao_antes_da_ia(tmp_path):
    audio = _wav(tmp_path / "conv.wav", [_fala(30, 1, 8, seed=5), _fala(30, 10, 7, seed=6)])
    with SessionLocal() as db:
        c = Call(id_ligacao=440001, caminho_audio=audio, status="pending",
                 tabulacao_operador="LIGAÇÃO MUDA / CAIXA POSTAL")
        db.add(c)
        db.commit()
        pipeline.qualificar_call(db, c)  # sem chave de IA: fica aguardando, mas já sinalizada
        assert c.status == "awaiting_ai"
        assert c.precisa_revisao is True and "fala" in c.revisao_motivo.lower()
        assert c.fala_segundos > 10


def test_muda_com_um_lado_so_nao_e_suspeita(tmp_path):
    audio = _wav(tmp_path / "solo.wav", [_fala(20, 1, 6), _silencio(20)])
    with SessionLocal() as db:
        c = Call(id_ligacao=440002, caminho_audio=audio, status="pending",
                 tabulacao_operador="LIGAÇÃO MUDA / CAIXA POSTAL")
        db.add(c)
        db.commit()
        pipeline.qualificar_call(db, c)
        assert not c.precisa_revisao


def test_ia_confirma_conversa_vira_divergencia_e_sai_da_revisao(tmp_path, monkeypatch):
    _IAFalsa(monkeypatch)
    audio = _wav(tmp_path / "conv2.wav", [_fala(30, 1, 8, seed=7), _fala(30, 10, 7, seed=8)])
    with SessionLocal() as db:
        c = Call(id_ligacao=440003, caminho_audio=audio, status="pending",
                 tabulacao_operador="LIGAÇÃO MUDA / CAIXA POSTAL")
        db.add(c)
        db.commit()
        pipeline.qualificar_call(db, c)
        assert c.status == "done" and c.divergencia_tabulacao is True
        assert not c.precisa_revisao  # a divergência confirmada já é o sinal


def test_falha_de_comunicacao_com_fala_dos_dois_lados_nao_e_suspeita():
    """Em 'falha de comunicação' os dois falam e não se ouvem: fala dos dois lados é o esperado."""
    base = dict(tabulacao_operador="LIGAÇÃO MUDA / CAIXA POSTAL", status="done", categoria="LIGACAO_MUDA",
                confianca=0.9, metricas_acusticas={"vad": True, "fala_segundos": 9, "fala_por_canal": [5, 4]})
    ok = Call(subcategoria="FALHA_COMUNICACAO", **base)
    pipeline.calcular_divergencia(ok)
    assert not ok.precisa_revisao
    estranho = Call(subcategoria="MUDO_TOTAL", **base)
    pipeline.calcular_divergencia(estranho)
    assert estranho.precisa_revisao and "dois lados" in estranho.revisao_motivo


# --------------------------------------------------------------------------- API
def test_api_filtra_revisao_e_mostra_custos(client):
    with SessionLocal() as db:
        db.add_all([
            Call(id_ligacao=450001, status="done", precisa_revisao=True, revisao_motivo="teste",
                 data_ligacao=datetime(2025, 3, 1, 9)),
            Call(id_ligacao=450002, status="done", data_ligacao=datetime(2025, 3, 1, 9)),
        ])
        db.commit()
    ids = [i["id_ligacao"] for i in client.get("/api/v1/calls", params={"revisao": "true", "page_size": 500}).json()["items"]]
    assert 450001 in ids and 450002 not in ids
    item = next(i for i in client.get("/api/v1/calls", params={"revisao": "true", "page_size": 500}).json()["items"]
                if i["id_ligacao"] == 450001)
    assert item["precisa_revisao"] is True and item["revisao_motivo"] == "teste" and "custo_usd" in item

    s = client.get("/api/v1/saude").json()
    for k in ("hoje_usd", "mes_usd", "custo_medio_usd", "resolvidas_sem_ia_mes", "teto_diario_usd", "serie"):
        assert k in s["custos"], k
    assert s["custos"]["hoje_usd"] > 0  # os testes acima registraram gasto hoje
    assert "revisao" in client.get("/api/v1/analytics/summary").json()


# --------------------------------------------------------------------------- scripts de validação
def test_validar_vad_aponta_conversa_que_seria_descartada(tmp_path):
    from scripts import validar_vad

    with SessionLocal() as db:
        db.add_all([
            Call(id_ligacao=460001, categoria="LIGACAO_MUDA", motor="csv", status="done",
                 caminho_audio=_wav(tmp_path / "v1.wav", [_silencio(6)])),
            Call(id_ligacao=460002, categoria="SEM_INTERESSE", motor="csv", status="done",
                 caminho_audio=_wav(tmp_path / "v2.wav", [_fala(10, 1, 5)])),
            Call(id_ligacao=460003, categoria="EM_NEGOCIACAO", motor="csv", status="done",
                 caminho_audio=_wav(tmp_path / "v3.wav", [_silencio(6)])),  # gabarito diz conversa, áudio mudo
        ])
        db.commit()
    r = validar_vad.avaliar()
    assert r["sem_fala"]["LIGACAO_MUDA"] >= 1
    assert [e[1] for e in r["erros"]] == [460003]


def test_comparar_transcricao_mede_acerto_e_custo(tmp_path, monkeypatch):
    from scripts import comparar_transcricao

    _IAFalsa(monkeypatch)  # sempre responde SEM_INTERESSE
    calls = [
        Call(id=1, categoria="SEM_INTERESSE", duracao_segundos=60, caminho_audio=_wav(tmp_path / "k1.wav", [_fala(5, 1, 2)])),
        Call(id=2, categoria="EM_NEGOCIACAO", duracao_segundos=60, caminho_audio=_wav(tmp_path / "k2.wav", [_fala(5, 1, 2)])),
    ]
    r = comparar_transcricao.avaliar(calls, ["whisper-1", "gpt-4o-mini-transcribe"])
    assert r["whisper-1"]["acuracia"] == 0.5 and r["gpt-4o-mini-transcribe"]["acertos"] == 1
    assert r["whisper-1"]["custo_usd"] > r["gpt-4o-mini-transcribe"]["custo_usd"] > 0
