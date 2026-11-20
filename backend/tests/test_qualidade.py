"""Semana 3: medir a IA. Revisão humana pela tela, gabarito, acurácia, calibração e amostra aleatória."""
from datetime import datetime

import pytest
from sqlalchemy import select

from app.config import settings
from app.database import SessionLocal
from app.models import Call
from app.services import pipeline, qualidade
from helpers import IAFalsa, fala, wav


def _ia(db, base, cat, sub=None, conf=0.9, tab="CLIENTE NÃO TEM INTERESSE", motor="openai", **kw) -> Call:
    """Ligação já qualificada pela IA (como o pipeline deixaria)."""
    c = Call(id_ligacao=base, status="done", categoria=cat, subcategoria=sub, categoria_ia=cat, subcategoria_ia=sub,
             confianca=conf, motor=motor, tabulacao_operador=tab, data_ligacao=datetime(2025, 7, 1, 9), **kw)
    db.add(c)
    db.flush()
    pipeline.atualizar_divergencia(db, c)
    db.commit()
    return c


def _revisar(client, cid, cat, sub=None, obs=None, revisor="Supervisora Ana"):
    return client.post(f"/api/v1/calls/{cid}/revisao",
                       json={"categoria": cat, "subcategoria": sub, "observacao": obs, "revisor": revisor})


# --------------------------------------------------------------------------- revisão pela tela
def test_corrigir_a_ia_muda_o_resultado_mas_guarda_a_resposta_original(client):
    with SessionLocal() as db:
        c = _ia(db, 710001, "EM_NEGOCIACAO", "PROPOSTA_EM_ANDAMENTO", tab="EM NEGOCIAÇÃO")
        assert c.divergencia_tabulacao is False
    r = _revisar(client, c.id, "SEM_INTERESSE", "CLIENTE_CALMO", "Só pediu o valor e recusou.")
    assert r.status_code == 200, r.text
    d = r.json()
    assert (d["categoria"], d["subcategoria"]) == ("SEM_INTERESSE", "CLIENTE_CALMO")
    assert (d["categoria_ia"], d["subcategoria_ia"]) == ("EM_NEGOCIACAO", "PROPOSTA_EM_ANDAMENTO")
    assert d["revisado"] and d["revisado_por"] == "Supervisora Ana" and d["revisao_observacao"]
    assert d["ia_acertou"] is False
    # a divergência passa a usar o resultado humano (negociação tabulada, mas foi recusa)
    assert d["divergencia_tabulacao"] is True and d["divergencia_gravidade"] == "alta"


def test_confirmar_a_ia_e_desfazer_a_revisao(client):
    with SessionLocal() as db:
        c = _ia(db, 710002, "SEM_INTERESSE", "CLIENTE_CALMO", conf=0.45, tab="EM NEGOCIAÇÃO")
        assert c.precisa_revisao is True and c.divergencia_tabulacao is False  # confiança baixa: não acusa
    d = _revisar(client, c.id, "SEM_INTERESSE", "CLIENTE_CALMO").json()
    assert d["ia_acertou"] is True and d["precisa_revisao"] is False
    assert d["divergencia_tabulacao"] is True, "com a confirmação humana, a divergência passa a valer"

    d = client.delete(f"/api/v1/calls/{c.id}/revisao").json()
    assert not d["revisado"] and d["categoria"] == "SEM_INTERESSE"
    assert d["precisa_revisao"] is True and d["divergencia_tabulacao"] is False


def test_humano_pode_marcar_inaudivel_sem_acusar_o_operador(client):
    with SessionLocal() as db:
        c = _ia(db, 710003, "EM_NEGOCIACAO", tab="CLIENTE NÃO TEM INTERESSE")
    d = _revisar(client, c.id, "INDETERMINADO", "AUDIO_INAUDIVEL").json()
    assert d["divergencia_tabulacao"] is False and d["precisa_revisao"] is False


def test_revisao_valida_categoria_e_revisor(client):
    with SessionLocal() as db:
        c = _ia(db, 710004, "SEM_INTERESSE")
    assert _revisar(client, c.id, "XYZ").status_code == 422
    assert _revisar(client, c.id, "SEM_INTERESSE", "ENGANO_DIRETO").status_code == 422
    assert _revisar(client, c.id, "SEM_INTERESSE", revisor="  ").status_code == 422
    assert _revisar(client, 99999999, "SEM_INTERESSE").status_code == 404
    with SessionLocal() as db:
        pend = Call(id_ligacao=710005, status="pending")
        db.add(pend)
        db.commit()
    assert _revisar(client, pend.id, "SEM_INTERESSE").status_code == 409, "só revisa ligação já analisada"


def test_reanalise_pela_ia_nao_apaga_a_revisao(tmp_path, monkeypatch, client):
    IAFalsa(monkeypatch)  # a IA responde SEM_INTERESSE / CLIENTE_CALMO
    with SessionLocal() as db:
        c = Call(id_ligacao=710006, status="pending", caminho_audio=wav(tmp_path / "r.wav", [fala(20, 1, 8)]),
                 tabulacao_operador="NÃO É O CLIENTE")
        db.add(c)
        db.commit()
        pipeline.qualificar_call(db, c)
    _revisar(client, c.id, "NAO_E_O_CLIENTE", "ENGANO_DIRETO")
    with SessionLocal() as db:
        c = db.get(Call, c.id)
        pipeline.qualificar_call(db, c, force=True)
        assert (c.categoria, c.categoria_ia) == ("NAO_E_O_CLIENTE", "SEM_INTERESSE")
        assert c.revisado_em is not None and c.divergencia_tabulacao is False


# --------------------------------------------------------------------------- fila de revisão e amostra
def test_amostra_aleatoria_e_deterministica_e_respeita_a_porcentagem(monkeypatch):
    monkeypatch.setattr(settings, "amostra_qualidade_pct", 10)
    sorteadas = [qualidade.na_amostra(Call(id_ligacao=i)) for i in range(5000)]
    assert 0.08 < sum(sorteadas) / 5000 < 0.12
    assert sorteadas == [qualidade.na_amostra(Call(id_ligacao=i)) for i in range(5000)]
    monkeypatch.setattr(settings, "amostra_qualidade_pct", 0)
    assert not any(qualidade.na_amostra(Call(id_ligacao=i)) for i in range(500))


def test_ligacao_sorteada_entra_na_fila_de_revisao(tmp_path, monkeypatch, client):
    IAFalsa(monkeypatch)
    monkeypatch.setattr(settings, "amostra_qualidade_pct", 100)
    with SessionLocal() as db:
        c = Call(id_ligacao=720001, status="pending", caminho_audio=wav(tmp_path / "a.wav", [fala(20, 1, 8)]),
                 tabulacao_operador="CLIENTE NÃO TEM INTERESSE")
        db.add(c)
        db.commit()
        pipeline.qualificar_call(db, c)
        assert c.na_amostra is True and c.precisa_revisao is False
    fila = client.get("/api/v1/calls", params={"revisao": "true", "page_size": 500}).json()["items"]
    item = next(i for i in fila if i["id"] == c.id)
    assert "amostra" in item["motivo_fila"].lower()
    _revisar(client, c.id, "SEM_INTERESSE", "CLIENTE_CALMO")
    fila = client.get("/api/v1/calls", params={"revisao": "true", "page_size": 500}).json()["items"]
    assert all(i["id"] != c.id for i in fila), "revisada sai da fila"
    feitas = client.get("/api/v1/calls", params={"revisado": "true", "page_size": 500}).json()["items"]
    assert any(i["id"] == c.id for i in feitas)


# --------------------------------------------------------------------------- escuta manual como gabarito
def test_csv_de_escuta_vira_revisao_humana(tmp_path, monkeypatch):
    from app.services import local_ingestor

    p = tmp_path / "escuta.csv"
    nome = "2026-11-05_081849_nr1_id730001_11988880000_FULANO.mp3"
    p.write_text(f"arquivo;categoria;subcategoria\n{nome};Cliente Não tem Interesse;Cliente calmo\n", encoding="utf-8")
    monkeypatch.setattr(settings, "recordings_dir", str(tmp_path))
    with SessionLocal() as db:
        local_ingestor.import_legacy_csv(db, str(p))
        c = db.scalars(select(Call).where(Call.id_ligacao == 730001)).one()
        assert c.categoria == "SEM_INTERESSE" and c.categoria_ia is None
        assert c.revisado_em is not None and "escuta" in c.revisado_por.lower()


# --------------------------------------------------------------------------- medição
def _cenario_qualidade(db, base=740000):
    """Revisões conhecidas: 8 avaliadas, 6 acertos."""
    casos = [  # (ia, humano, confiança, motor)
        ("SEM_INTERESSE", "SEM_INTERESSE", 0.95, "openai"),
        ("SEM_INTERESSE", "SEM_INTERESSE", 0.9, "openai"),
        ("SEM_INTERESSE", "NAO_E_O_CLIENTE", 0.55, "openai"),
        ("EM_NEGOCIACAO", "EM_NEGOCIACAO", 0.85, "openai"),
        ("EM_NEGOCIACAO", "SEM_INTERESSE", 0.7, "openai"),
        ("NAO_E_O_CLIENTE", "NAO_E_O_CLIENTE", 0.65, "openai"),
        ("LIGACAO_MUDA", "LIGACAO_MUDA", 0.95, "local"),
        ("LIGACAO_MUDA", "LIGACAO_MUDA", 0.95, "local"),
    ]
    ids = []
    for i, (ia, hum, conf, motor) in enumerate(casos):
        c = _ia(db, base + i, ia, conf=conf, motor=motor, tab="CLIENTE NÃO TEM INTERESSE")
        qualidade.revisar(db, c, hum, None, "Teste", None)
        ids.append(c.id)
    db.commit()
    return ids


def test_medicao_de_acuracia_matriz_e_calibracao():
    with SessionLocal() as db:
        ids = _cenario_qualidade(db)
        m = qualidade.medir(db, ids=set(ids))
    assert m["avaliadas"] == 8 and m["acertos"] == 6 and m["acuracia"] == 75.0
    cat = {c["codigo"]: c for c in m["por_categoria"]}
    assert cat["SEM_INTERESSE"]["humano"] == 3 and cat["SEM_INTERESSE"]["ia"] == 3
    assert cat["SEM_INTERESSE"]["precisao"] == pytest.approx(66.7) and cat["SEM_INTERESSE"]["recall"] == pytest.approx(66.7)
    assert cat["LIGACAO_MUDA"]["precisao"] == 100.0
    linha = next(l for l in m["confusao"]["linhas"] if l["humano"] == "NAO_E_O_CLIENTE")
    assert linha["ia"] == {"SEM_INTERESSE": 1, "NAO_E_O_CLIENTE": 1}
    faixas = {f["faixa"]: f for f in m["por_confianca"]}
    assert faixas["abaixo de 60%"]["n"] == 1 and faixas["abaixo de 60%"]["acuracia"] == 0
    assert faixas["80% ou mais"]["acuracia"] == 100.0
    motores = {x["motor"]: x for x in m["por_motor"]}
    assert motores["local"]["acuracia"] == 100.0 and motores["openai"]["n"] == 6
    assert len(m["discordancias"]) == 2


def test_precisao_das_divergencias_apontadas_pela_ia():
    """Das divergências que a IA apontou e alguém revisou, quantas o humano confirmou?"""
    with SessionLocal() as db:
        ids = _cenario_qualidade(db, base=741000)
        m = qualidade.medir(db, ids=set(ids))
    d = m["divergencias"]
    # tabulação "sem interesse": IA apontou divergência em EM_NEG(0.85), EM_NEG(0.7), NAO_E(0.65), 2x MUDA (5 casos);
    # humano confirma EM_NEG(0.85), NAO_E(0.65), 2x MUDA (4) e desfaz EM_NEG->SEM_INTERESSE (1)
    assert d["apontadas"] == 5 and d["confirmadas"] == 4 and d["precisao"] == 80.0
    # e a IA deixou passar uma: SEM_INTERESSE -> humano NAO_E_O_CLIENTE (conf 0.55 foi para revisão, não acusou)
    assert d["perdidas"] == 1


def test_api_qualidade_e_medir_com_gabarito(client, monkeypatch):
    r = client.get("/api/v1/qualidade")
    assert r.status_code == 200
    j = r.json()
    for k in ("avaliadas", "acuracia", "por_categoria", "confusao", "por_confianca", "por_motor", "divergencias",
              "fila", "gabarito", "discordancias"):
        assert k in j, k
    monkeypatch.setattr(settings, "openai_api_key", "")
    assert client.post("/api/v1/qualidade/medir", params={"n": 10}).status_code == 400


def test_medir_reanalisa_so_o_gabarito_sem_resposta_da_ia(client, monkeypatch):
    from app import worker

    enfileiradas = []
    monkeypatch.setattr(settings, "openai_api_key", "sk-teste")
    monkeypatch.setattr(worker, "enqueue", lambda cid, force=False: enfileiradas.append((cid, force)) or True)
    with SessionLocal() as db:
        g = Call(id_ligacao=750001, status="done", categoria="SEM_INTERESSE", motor="csv", transcricao="não quero",
                 duracao_segundos=60, revisado_em=datetime(2025, 1, 1), revisado_por="Escuta manual (CSV)",
                 categoria_revisada="SEM_INTERESSE")
        ja = _ia(db, 750002, "SEM_INTERESSE")
        qualidade.revisar(db, ja, "SEM_INTERESSE", None, "Teste", None)
        db.add(g)
        db.commit()
    r = client.post("/api/v1/qualidade/medir", params={"n": 500}).json()
    ids = {cid for cid, _ in enfileiradas}
    assert g.id in ids and ja.id not in ids and all(force for _, force in enfileiradas)
    assert r["enfileiradas"] == len(enfileiradas) and r["custo_estimado_usd"] > 0
