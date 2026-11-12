"""Etapa 2 do custo: cortar silêncio antes de transcrever e separar operador/cliente pelo estéreo."""
from pathlib import Path

import numpy as np
import pytest
from sqlalchemy import select

from app.config import settings
from app.database import SessionLocal
from app.models import Call, IaUso
from app.services import audio_analyzer as aa
from app.services import custos, pipeline
from helpers import IAFalsa, fala, silencio, wav


def _dur(path: str) -> float:
    return len(aa.carregar(path)) / aa.TAXA


def _energia(x: np.ndarray) -> float:
    return float((x.astype(np.float64) ** 2).sum())


def _nova(db, id_ligacao: int, audio: str, **kw) -> Call:
    c = Call(id_ligacao=id_ligacao, caminho_audio=audio, status="pending", **kw)
    db.add(c)
    db.commit()
    return c


# --------------------------------------------------------------------------- corte de silêncio
def test_corte_remove_espera_longa_e_preserva_toda_a_fala(tmp_path):
    p = wav(tmp_path / "a.wav", [fala(60, 1, 30)])  # 30 s de voz + 29 s de espera muda no fim
    partes = aa.preparar_para_transcricao(p)
    assert len(partes) == 1 and partes[0].lado is None
    assert 31 < partes[0].segundos < 34, "sobra a fala + margens de silêncio"
    assert partes[0].segundos_original == pytest.approx(60, abs=0.5)
    original, cortado = aa.carregar(p)[:, 0], aa.carregar(partes[0].arquivo)[:, 0]
    assert _energia(cortado) > 0.995 * _energia(original), "nenhum trecho de voz pode ser cortado"
    aa.limpar(partes)
    assert not Path(partes[0].arquivo).exists()


def test_pausas_curtas_da_conversa_nao_sao_cortadas(tmp_path):
    x = fala(12, 1, 3).copy()
    x += fala(12, 5.2, 3, seed=9) - silencio(12)  # segunda fala 1,2 s depois da primeira
    p = wav(tmp_path / "b.wav", [x[: 9 * 8000]])
    partes = aa.preparar_para_transcricao(p)
    # economia < 10%: manda o arquivo original, sem recodificar
    assert partes[0].arquivo == p and partes[0].temporario is False
    assert partes[0].segundos == pytest.approx(9, abs=0.3)


def test_voz_baixa_entre_falas_nao_e_cortada(tmp_path):
    """O corte usa um limiar mais sensível que o da detecção de fala: na dúvida, mantém."""
    x = fala(40, 1, 5).copy()
    a, b = 15 * 8000, 20 * 8000
    x[a:b] += np.random.default_rng(4).normal(0, 0.002, b - a)  # voz bem baixa (-54 dBFS) no meio da espera
    p = wav(tmp_path / "c.wav", [x])
    partes = aa.preparar_para_transcricao(p)
    cortado, original = aa.carregar(partes[0].arquivo)[:, 0], aa.carregar(p)[:, 0]
    trecho = original[15 * aa.TAXA: 20 * aa.TAXA]
    assert _energia(cortado) > 0.995 * _energia(original)
    assert _energia(trecho) > 0 and partes[0].segundos > 5 + 5  # os 5 s de voz baixa continuam lá


def test_corte_desligado_envia_o_arquivo_original(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "cortar_silencio", False)
    p = wav(tmp_path / "d.wav", [fala(60, 1, 30)])
    partes = aa.preparar_para_transcricao(p)
    assert partes[0].arquivo == p and partes[0].segundos == pytest.approx(60, abs=0.5)


def test_analise_estima_a_duracao_apos_o_corte(tmp_path):
    m = aa.analyze(wav(tmp_path / "e.wav", [fala(60, 1, 30)]))
    assert 31 < m["duracao_apos_corte"] < 34


# --------------------------------------------------------------------------- estéreo: um lado por canal
def _conversa(tmp_path, nome="conv.wav"):
    """Operador fala de 1 a 9 s (canal 0); cliente de 10 a 17 s (canal 1). 30 s no total."""
    return wav(tmp_path / nome, [fala(30, 1, 8, seed=5), fala(30, 10, 7, seed=6)])


def test_estereo_gera_uma_parte_por_lado(tmp_path):
    partes = aa.preparar_para_transcricao(_conversa(tmp_path))
    assert [p.lado for p in partes] == ["ATENDENTE", "CLIENTE"]
    assert 8 < partes[0].segundos < 10.5 and 7 < partes[1].segundos < 9.5
    assert sum(p.segundos for p in partes) < 20, "cada lado vai sem o silêncio de quando o outro fala"
    aa.limpar(partes)


def test_canal_do_operador_e_configuravel(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "argus_canal_operador", 1)
    partes = aa.preparar_para_transcricao(_conversa(tmp_path))
    assert [p.lado for p in partes] == ["CLIENTE", "ATENDENTE"]
    aa.limpar(partes)


def test_lado_sem_fala_nao_e_transcrito(tmp_path):
    partes = aa.preparar_para_transcricao(wav(tmp_path / "solo.wav", [fala(20, 1, 6), silencio(20)]))
    assert partes[0].lado == "ATENDENTE" and partes[0].arquivo
    assert partes[1].lado == "CLIENTE" and partes[1].arquivo is None and partes[1].segundos == 0
    aa.limpar(partes)


def test_mono_duplicado_nao_e_tratado_como_dois_lados(tmp_path):
    x = fala(20, 1, 6)
    partes = aa.preparar_para_transcricao(wav(tmp_path / "dup.wav", [x, x]))
    assert len(partes) == 1 and partes[0].lado is None
    aa.limpar(partes)


def test_separacao_por_canal_pode_ser_desligada(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "transcricao_por_canal", False)
    partes = aa.preparar_para_transcricao(_conversa(tmp_path))
    assert len(partes) == 1 and partes[0].lado is None
    aa.limpar(partes)


def test_arquivo_ilegivel_cai_para_o_original(tmp_path):
    p = tmp_path / "ruim.mp3"
    p.write_bytes(b"\x00" * 64)
    partes = aa.preparar_para_transcricao(str(p))
    assert len(partes) == 1 and partes[0].arquivo == str(p) and partes[0].temporario is False


# --------------------------------------------------------------------------- pipeline
def test_pipeline_cobra_so_os_segundos_enviados(tmp_path, monkeypatch):
    ia = IAFalsa(monkeypatch)
    monkeypatch.setattr(settings, "openai_whisper_model", "whisper-1")
    with SessionLocal() as db:
        c = _nova(db, 510001, wav(tmp_path / "p1.wav", [fala(60, 1, 30)]))
        pipeline.qualificar_call(db, c)
        u = db.scalars(select(IaUso).where(IaUso.call_id == c.id, IaUso.tipo == "transcricao")).one()
        assert 31 < u.audio_segundos < 34 and u.audio_segundos_original == pytest.approx(60, abs=0.5)
        assert u.custo_usd == pytest.approx(u.audio_segundos / 60 * 0.006)
        assert c.status == "done"
    assert not Path(ia.arquivos[0]).exists(), "o arquivo temporário cortado é apagado depois do envio"


def test_pipeline_estereo_transcreve_cada_lado_e_identifica_quem_falou(tmp_path, monkeypatch):
    ia = IAFalsa(monkeypatch)
    ia.fala_por_arquivo = lambda p: "bom dia, falo com a dona Maria?" if "ATENDENTE" in p else "não tenho interesse"
    with SessionLocal() as db:
        c = _nova(db, 510002, _conversa(tmp_path, "p2.wav"))
        pipeline.qualificar_call(db, c)
        assert ia.transcricoes == 2
        assert c.transcricao == "ATENDENTE: bom dia, falo com a dona Maria?\nCLIENTE: não tenho interesse"
        assert ia.textos[-1] == c.transcricao, "a IA recebe o texto já identificado por lado"
        assert c.transcricao_diarizada == [
            {"speaker": "ATENDENTE", "text": "bom dia, falo com a dona Maria?", "sentiment": None},
            {"speaker": "CLIENTE", "text": "não tenho interesse", "sentiment": None},
        ]
        assert c.metricas_acusticas["transcricao_por_canal"] is True
        usos = db.scalars(select(IaUso).where(IaUso.call_id == c.id, IaUso.tipo == "transcricao")).all()
        assert len(usos) == 2 and sum(u.audio_segundos for u in usos) < 20


def test_pipeline_estereo_com_um_lado_mudo_transcreve_so_o_outro(tmp_path, monkeypatch):
    ia = IAFalsa(monkeypatch)
    ia.fala_por_arquivo = lambda p: "alô? alô?"
    with SessionLocal() as db:
        c = _nova(db, 510003, wav(tmp_path / "p3.wav", [fala(20, 1, 6), silencio(20)]))
        pipeline.qualificar_call(db, c)
        assert ia.transcricoes == 1
        assert c.transcricao.startswith("ATENDENTE: alô? alô?\nCLIENTE: (sem fala detectada")
        assert [t["speaker"] for t in c.transcricao_diarizada] == ["ATENDENTE"]
        assert c.status == "done", "a IA continua decidindo a categoria (100% auditado)"


def test_reanalise_mantem_os_lados_sem_transcrever_de_novo(tmp_path, monkeypatch):
    ia = IAFalsa(monkeypatch)
    ia.fala_por_arquivo = lambda p: "oi" if "ATENDENTE" in p else "tchau"
    with SessionLocal() as db:
        c = _nova(db, 510004, _conversa(tmp_path, "p4.wav"))
        pipeline.qualificar_call(db, c)
        pipeline.qualificar_call(db, c, force=True)
        assert ia.transcricoes == 2 and ia.classificacoes == 2
        assert [t["text"] for t in c.transcricao_diarizada] == ["oi", "tchau"]


def test_falha_no_segundo_lado_preserva_o_que_ja_foi_pago(tmp_path, monkeypatch):
    ia = IAFalsa(monkeypatch)

    def _falha_no_cliente(p):
        if "CLIENTE" in p:
            raise TimeoutError("timeout")
        return "bom dia"

    ia.fala_por_arquivo = _falha_no_cliente
    with SessionLocal() as db:
        c = _nova(db, 510005, _conversa(tmp_path, "p5.wav"))
        pipeline.qualificar_call(db, c)
        assert c.status == "error" and c.categoria is None
        usos = db.scalars(select(IaUso).where(IaUso.call_id == c.id)).all()
        assert [u.tipo for u in usos] == ["transcricao"], "o lado já transcrito é contabilizado"
    assert all(not Path(a).exists() for a in ia.arquivos), "temporários apagados mesmo com falha"


def test_painel_mostra_minutos_economizados_pelo_corte(tmp_path, monkeypatch, client):
    IAFalsa(monkeypatch)
    with SessionLocal() as db:
        c = _nova(db, 510006, wav(tmp_path / "p6.wav", [fala(120, 1, 20)]))
        pipeline.qualificar_call(db, c)
        r = custos.resumo(db)
    assert r["minutos_economizados_mes"] >= 1.5
    assert "minutos_economizados_mes" in client.get("/api/v1/saude").json()["custos"]


def test_script_compara_audio_inteiro_com_tratado(tmp_path, monkeypatch):
    from scripts import comparar_transcricao

    IAFalsa(monkeypatch)  # sempre responde SEM_INTERESSE
    calls = [Call(id=1, categoria="SEM_INTERESSE", duracao_segundos=60, caminho_audio=wav(tmp_path / "s1.wav", [fala(60, 1, 20)]))]
    r = comparar_transcricao.avaliar(calls, ["whisper-1", "whisper-1+tratado"])
    assert r["whisper-1"]["acuracia"] == r["whisper-1+tratado"]["acuracia"] == 1
    assert r["whisper-1"]["minutos"] == pytest.approx(1.0, abs=0.02)
    assert r["whisper-1+tratado"]["minutos"] < 0.45 and r["whisper-1+tratado"]["custo_usd"] < r["whisper-1"]["custo_usd"]


def test_validar_vad_estima_a_economia_do_corte(tmp_path):
    from scripts import validar_vad

    with SessionLocal() as db:
        db.add(Call(id_ligacao=520001, categoria="SEM_INTERESSE", motor="csv", status="done",
                    caminho_audio=wav(tmp_path / "vv.wav", [fala(100, 1, 20)])))
        db.commit()
    r = validar_vad.avaliar()
    assert r["minutos_apos_corte"] < r["minutos_com_fala"]
