# O banco temporário é configurado em conftest.py
from datetime import datetime

import pytest

from app.database import SessionLocal, init_db
from app.models import Call
from app.services import local_ingestor, pipeline


def test_parse_filename():
    m = local_ingestor.parse_filename(
        "2026-11-05_081849_nr120917973_id181398178_93992370580_HOSANA SANTANA DA SILVA.mp3")
    assert m["id_ligacao"] == 181398178 and m["telefone"] == "93992370580"
    assert m["data_ligacao"] == datetime(2026, 11, 5, 8, 18, 49)
    assert local_ingestor.parse_filename("2026-11-05_123506_nr1_id2_9_.mp3")["nome_esperado"] is None


def test_identidade_historico():
    init_db()
    with SessionLocal() as db:
        a = Call(id_ligacao=9001, telefone="11999990000", nome_esperado="ELDER VALLEJO", status="avaliada",
                 categoria="SEM_INTERESSE", subcategoria="CLIENTE_CALMO",
                 data_ligacao=datetime(2026, 11, 4, 10))
        db.add(a)
        db.flush()
        pipeline.resolver_identidade(db, a)
        b = Call(id_ligacao=9002, telefone="11999990000", nome_esperado="Elder Vallejo", status="avaliada",
                 categoria="NAO_E_O_CLIENTE", subcategoria="ENGANO_DIRETO",
                 data_ligacao=datetime(2026, 11, 5, 10))
        db.add(b)
        db.flush()
        pipeline.resolver_identidade(db, b)
        db.commit()
        assert b.subcategoria == "E_O_CLIENTE_HISTORICO" and b.conflito_identidade
        assert b.ligacao_referencia_id == a.id


def test_webhook_e_filtros_de_data(client):
    p = {"idTipoWebhook": 2, "idCampanha": 7, "nrLead": 5, "nomeCliente": "FULANO", "idLigacao": 777,
         "dataInicioLigacao": "2026-11-05 09:00:00", "tempoLigacao": 33, "telefone": "11988887777",
         "nomeUsuario": "Ana", "codUsuarioIntegracao": "1001", "tabulacaoDesc": "Sem interesse"}
    r = client.post("/api/v1/webhooks/argus", json=p)
    assert r.status_code == 200 and r.json()["ok"]
    assert client.post("/api/v1/webhooks/argus", json={"idTipoWebhook": 2, "idLigacao": 0}).json()["ok"]
    j = client.get("/api/v1/calls", params={"data_inicio": "2026-11-05", "data_fim": "2026-11-05"}).json()
    assert any(i["id_ligacao"] == 777 and i["operador_nome"] == "Ana" for i in j["items"])
    j = client.get("/api/v1/calls", params={"data_inicio": "2026-11-06"}).json()
    assert all(i["id_ligacao"] != 777 for i in j["items"])
    assert client.get("/api/v1/analytics/summary", params={"data_inicio": "2026-11-05"}).status_code == 200
    assert client.get("/api/v1/analytics/timeline").status_code == 200
