"""Monitoria humana (fase 1): sem IA, o resultado da ligação vem da monitora."""
import time
from datetime import datetime

import pytest
from sqlalchemy import func, select

from app.config import settings
from app.database import SessionLocal
from app.models import Avaliacao, Call
from app.services import argus_client, local_ingestor, pipeline
from helpers import wav


def _call(**kw) -> int:
    base = dict(status="pendente_avaliacao", caminho_audio="/tmp/x.mp3", data_ligacao=datetime(2025, 7, 1, 10))
    with SessionLocal() as db:
        c = Call(**{**base, **kw})
        db.add(c)
        db.commit()
        return c.id


def _esperar_status(call_id: int, diferente_de: str, segundos: float = 5) -> Call:
    fim = time.time() + segundos
    while True:
        with SessionLocal() as db:
            c = db.get(Call, call_id)
            if c.status != diferente_de or time.time() > fim:
                return c
        time.sleep(0.05)


# --------------------------------------------------------------------------- chegada da ligação
def test_ligacao_do_webhook_fica_pendente_de_avaliacao(client, monkeypatch, tmp_path):
    audio = tmp_path / "g.mp3"
    audio.write_bytes(b"\x00" * 64)
    monkeypatch.setattr(argus_client, "download_gravacao", lambda camp, lig: audio)
    p = {"idTipoWebhook": 2, "idCampanha": 7, "idLigacao": 940001, "tempoLigacao": 42,
         "dataInicioLigacao": "2025-07-01 09:00:00", "tabulacaoDesc": "CLIENTE NÃO TEM INTERESSE"}
    r = client.post("/api/v1/webhooks/argus", json=p)
    assert r.status_code == 200 and r.json()["enfileirado"] is True
    c = _esperar_status(r.json()["id"], "pendente")
    assert c.status == "pendente_avaliacao"
    assert c.caminho_audio == str(audio) and c.erro is None
    assert c.categoria is None and c.divergencia_tabulacao is False, "sem avaliação, não há resultado nem divergência"


def test_falha_no_download_marca_erro(monkeypatch):
    def _explode(*a, **k):
        raise argus_client.ArgusError("gravação não encontrada")

    monkeypatch.setattr(argus_client, "download_gravacao", _explode)
    with SessionLocal() as db:
        c = Call(id_ligacao=940101, origem="argus", id_campanha=7, status="pendente")
        db.add(c)
        db.commit()
        pipeline.preparar_call(db, c)
        assert c.status == "erro" and "download" in c.erro


def test_audio_local_vai_direto_para_a_fila_de_avaliacao(tmp_path):
    audio = tmp_path / "l.mp3"
    audio.write_bytes(b"\x00" * 64)
    with SessionLocal() as db:
        c = Call(id_ligacao=940201, origem="local", status="pendente", caminho_audio=str(audio))
        db.add(c)
        db.commit()
        pipeline.preparar_call(db, c)
        assert c.status == "pendente_avaliacao"


def test_baixar_de_novo_nao_desfaz_a_avaliacao(client, monkeypatch, tmp_path):
    novo = tmp_path / "novo.mp3"
    novo.write_bytes(b"\x00" * 64)
    monkeypatch.setattr(argus_client, "download_gravacao", lambda camp, lig: novo)
    cid = _call(id_ligacao=940301, origem="argus", id_campanha=7, caminho_audio="/nao/existe.mp3")
    assert client.post(f"/api/v1/calls/{cid}/resultado", json={"categoria": "SEM_INTERESSE"}).status_code == 200
    r = client.post(f"/api/v1/sync/reprocess/{cid}")
    assert r.status_code == 200 and r.json()["enfileirada"] is True
    fim = time.time() + 5
    while time.time() < fim:
        with SessionLocal() as db:
            c = db.get(Call, cid)
            if c.caminho_audio == str(novo):
                break
        time.sleep(0.05)
    assert c.caminho_audio == str(novo) and c.status == "avaliada" and c.categoria == "SEM_INTERESSE"


# --------------------------------------------------------------------------- resultado da ligação
def test_monitora_registra_o_resultado_e_a_divergencia_e_calculada(client):
    cid = _call(id_ligacao=941001, tabulacao_operador="CLIENTE NÃO TEM INTERESSE")
    r = client.post(f"/api/v1/calls/{cid}/resultado",
                    json={"categoria": "EM_NEGOCIACAO", "subcategoria": "PROPOSTA_EM_ANDAMENTO"})
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["status"] == "avaliada" and b["categoria"] == "EM_NEGOCIACAO"
    assert b["divergencia_tabulacao"] is True and b["divergencia_gravidade"] == "alta"
    assert "monitoria identificou" in b["divergencia_detalhe"]
    assert b["avaliacao"]["status"] == "finalizada" and b["avaliacao"]["origem"] == "tela"
    primeira = b["avaliacao"]["id"]

    # corrigir o resultado atualiza a mesma avaliação
    b = client.post(f"/api/v1/calls/{cid}/resultado", json={"categoria": "SEM_INTERESSE", "pediu_nao_ligar": True}).json()
    assert b["divergencia_tabulacao"] is False and b["pediu_nao_ligar"] is True
    assert b["avaliacao"]["id"] == primeira
    with SessionLocal() as db:
        assert db.scalar(select(func.count(Avaliacao.id)).where(Avaliacao.call_id == cid)) == 1
        assert db.get(Avaliacao, primeira).pediu_nao_ligar is True


def test_ligacao_nao_avaliavel(client):
    cid = _call(id_ligacao=941101, tabulacao_operador="EM NEGOCIAÇÃO")
    r = client.post(f"/api/v1/calls/{cid}/resultado", json={"nao_avaliavel": True, "motivo": "Áudio cortado"})
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["status"] == "nao_avaliavel" and b["categoria"] is None and b["divergencia_tabulacao"] is False
    assert b["avaliacao"]["status"] == "nao_avaliavel" and b["avaliacao"]["nao_avaliavel_motivo"] == "Áudio cortado"


def test_resultado_e_validado(client):
    cid = _call(id_ligacao=941201)
    url = f"/api/v1/calls/{cid}/resultado"
    assert client.post(url, json={"categoria": "INEXISTENTE"}).status_code == 422
    assert client.post(url, json={"categoria": "SEM_INTERESSE", "subcategoria": "ENGANO_DIRETO"}).status_code == 422
    assert client.post(url, json={}).status_code == 422
    assert client.post(url, json={"nao_avaliavel": True}).status_code == 422, "precisa do motivo"
    assert client.post("/api/v1/calls/99999999/resultado", json={"categoria": "SEM_INTERESSE"}).status_code == 404
    sem_audio = _call(id_ligacao=941202, status="pendente", caminho_audio=None)
    assert client.post(f"/api/v1/calls/{sem_audio}/resultado", json={"categoria": "SEM_INTERESSE"}).status_code == 409


def test_sem_avaliacao_nao_ha_divergencia():
    c = Call(status="pendente_avaliacao", tabulacao_operador="CLIENTE NÃO TEM INTERESSE", categoria="EM_NEGOCIACAO")
    pipeline.calcular_divergencia(c)
    assert c.divergencia_tabulacao is False and c.divergencia_gravidade is None
    c.status = "avaliada"
    pipeline.calcular_divergencia(c)
    assert c.divergencia_tabulacao is True


# --------------------------------------------------------------------------- painel
def test_resumo_mostra_avaliadas_e_nao_avaliadas(client):
    dia = datetime(2024, 4, 2, 10)
    for i, st in enumerate(["pendente_avaliacao", "pendente_avaliacao", "pendente", "avaliada", "nao_avaliavel"]):
        _call(id_ligacao=942000 + i, status=st, data_ligacao=dia, tabulacao_operador="CLIENTE NÃO TEM INTERESSE",
              categoria="SEM_INTERESSE" if st == "avaliada" else None)
    s = client.get("/api/v1/analytics/summary", params={"data_inicio": "2024-04-02", "data_fim": "2024-04-02"}).json()
    assert (s["total"], s["avaliadas"], s["nao_avaliadas"], s["aguardando_avaliacao"]) == (5, 1, 3, 2)
    for chave in ("confianca_media", "sem_ia", "custo_usd", "revisao"):
        assert chave not in s
    linha = next(m for m in s["matriz_contraste"] if m["tabulacao_operador"] == "CLIENTE NÃO TEM INTERESSE")
    assert linha["categorias"] == {"SEM_INTERESSE": 1, "NAO_AVALIADA": 3, "NAO_AVALIAVEL": 1}

    fila = client.get("/api/v1/calls", params={"data_inicio": "2024-04-02", "data_fim": "2024-04-02",
                                               "revisao": "true"}).json()
    assert fila["total"] == 2 and all(i["status"] == "pendente_avaliacao" for i in fila["items"])


def test_ligacao_nao_expoe_dados_de_ia(client):
    cid = _call(id_ligacao=943001)
    c = client.get(f"/api/v1/calls/{cid}").json()
    for chave in ("confianca", "motor", "resumo", "evidencia", "transcricao", "transcricao_diarizada",
                  "metricas_acusticas", "categoria_ia", "custo_usd", "fala_segundos", "ia_acertou"):
        assert chave not in c
    assert c["avaliacao"] is None and c["status"] == "pendente_avaliacao"


def test_rotas_de_ia_sairam(client):
    assert client.get("/api/v1/qualidade").status_code == 404
    cid = _call(id_ligacao=943101)
    assert client.post(f"/api/v1/calls/{cid}/revisao", json={"categoria": "SEM_INTERESSE"}).status_code in (404, 405)
    h = client.get("/health").json()
    assert "ia" not in h and h["ok"] is True
    s = client.get("/api/v1/saude").json()
    assert "custos" not in s and "ia" not in s["integracoes"]
    assert set(s["status_ligacoes"]) == {"pendente", "pendente_avaliacao", "em_avaliacao", "avaliada",
                                         "nao_avaliavel", "erro"}


# --------------------------------------------------------------------------- escuta manual importada
def test_escuta_manual_importada_vira_avaliacao(tmp_path, monkeypatch):
    rec = tmp_path / "rec"
    rec.mkdir()
    monkeypatch.setattr(settings, "recordings_dir", str(rec))
    nome = "2025-07-02_100000_nr1_id944001_11988880000_MARIA.mp3"
    (rec / nome).write_bytes(b"\x00" * 32)
    csv_path = tmp_path / "escuta.csv"
    csv_path.write_text("Arquivo;Categoria;Subcategoria\n" f"{nome};Cliente Não tem Interesse;Cliente calmo\n",
                        encoding="utf-8")
    with SessionLocal() as db:
        res = local_ingestor.import_legacy_csv(db, str(csv_path))
        assert res["qualificadas_pelo_csv"] == 1
        c = db.scalars(select(Call).where(Call.id_ligacao == 944001)).one()
        a = db.get(Avaliacao, c.avaliacao_id)
        assert c.status == "avaliada" and (c.categoria, c.subcategoria) == ("SEM_INTERESSE", "CLIENTE_CALMO")
        assert a.origem == "importada" and a.status == "finalizada" and a.monitora_nome == "Escuta manual (CSV)"
        # importar de novo não cria outra avaliação
        local_ingestor.import_legacy_csv(db, str(csv_path))
        assert db.scalar(select(func.count(Avaliacao.id)).where(Avaliacao.call_id == c.id)) == 1


def test_duracao_do_audio_vem_do_mutagen(tmp_path):
    assert pipeline.duracao_audio(wav(tmp_path / "d.wav", 3)) == pytest.approx(3, abs=0.05)
    assert pipeline.duracao_audio(str(tmp_path / "nao_existe.mp3")) is None


def test_baixar_gravacoes_pendentes(client, monkeypatch):
    from app import worker
    from app.database import SessionLocal
    from app.models import Call

    fila = []
    monkeypatch.setattr(worker, "enqueue", lambda cid, force=False: fila.append(cid) or True)
    with SessionLocal() as db:
        p = Call(id_ligacao=990001, status="pendente")
        e = Call(id_ligacao=990002, status="erro")
        ok = Call(id_ligacao=990003, status="avaliada")
        db.add_all([p, e, ok])
        db.commit()
        ids = {p.id, e.id}
        ok_id = ok.id
    r = client.post("/api/v1/sync/process").json()
    assert ids <= set(fila) and ok_id not in fila and r["enfileiradas"] == len(fila)
