import os
import tempfile

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/t.db"
os.environ["OPENAI_API_KEY"] = ""

from datetime import datetime  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.database import SessionLocal, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Call  # noqa: E402
from app.services import ai_qualifier, local_ingestor, pipeline  # noqa: E402


@pytest.fixture(scope="module")
def client():
    init_db()
    with TestClient(app) as c:
        yield c


def test_parse_filename():
    m = local_ingestor.parse_filename(
        "2026-11-05_081849_nr120917973_id181398178_93992370580_HOSANA SANTANA DA SILVA.mp3")
    assert m["id_ligacao"] == 181398178 and m["telefone"] == "93992370580"
    assert m["data_ligacao"] == datetime(2026, 11, 5, 8, 18, 49)
    assert local_ingestor.parse_filename("2026-11-05_123506_nr1_id2_9_.mp3")["nome_esperado"] is None


@pytest.mark.parametrize("txt,sub", [
    ("maria neuza esse número ela morreu", "TITULAR_FALECIDO"),
    ("não conheço essa pessoa moço, desculpa", "ENGANO_DIRETO"),
    ("não é ela, é do meu esposo, ele só chega de noite", "TERCEIRO_FAMILIA"),
    ("não é ela, vocês ligam todo dia pra esse número", "RECLAMACAO_RECORRENTE"),
])
def test_heuristica_nao_e_cliente(txt, sub):
    r = ai_qualifier.heuristica(txt + " " * 3, 20)
    assert r.categoria == "NAO_E_O_CLIENTE" and r.subcategoria == sub


def test_heuristica_outras():
    assert ai_qualifier.heuristica("Deixe seu recado após o sinal", 10).categoria == "CAIXA_POSTAL"
    assert ai_qualifier.heuristica("", 5).subcategoria == "MUDO_TOTAL"
    r = ai_qualifier.heuristica("não aguento mais, pare de ligar, que saco", 12)
    assert r.subcategoria == "CLIENTE_REVOLTADO"


def test_identidade_historico():
    init_db()
    with SessionLocal() as db:
        a = Call(id_ligacao=9001, telefone="11999990000", nome_esperado="ELDER VALLEJO", status="done",
                 categoria="SEM_INTERESSE", subcategoria="CLIENTE_CALMO", confianca=0.9,
                 data_ligacao=datetime(2026, 11, 4, 10))
        db.add(a)
        db.flush()
        pipeline.resolver_identidade(db, a)
        b = Call(id_ligacao=9002, telefone="11999990000", nome_esperado="Elder Vallejo", status="done",
                 categoria="NAO_E_O_CLIENTE", subcategoria="ENGANO_DIRETO", confianca=0.8,
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


def test_qualificar_fallback():
    r = ai_qualifier.qualificar(None, "João", "11999991111", 10.0, "Alô, não conheço nenhum João")
    assert r.categoria == "NAO_E_O_CLIENTE"
    assert r.motor in ("heuristica", "openai")


def test_openai_structured_schema():
    from openai.lib._parsing import type_to_response_format_param
    schema = type_to_response_format_param(ai_qualifier.Resultado)
    assert schema["type"] == "json_schema"
    assert "categoria" in schema["json_schema"]["schema"]["properties"]
    assert "turnos" in schema["json_schema"]["schema"]["properties"]

