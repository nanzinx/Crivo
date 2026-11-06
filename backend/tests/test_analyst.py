from datetime import datetime

import pytest

from app.database import SessionLocal
from app.models import Call
from app.services import pipeline


def test_divergencia_logic():
    call = Call(
        tabulacao_operador="CLIENTE NÃO TEM INTERESSE",
        categoria="EM_NEGOCIACAO",
    )
    pipeline.calcular_divergencia(call)
    assert call.divergencia_tabulacao is True
    assert "Operador tabulou" in (call.divergencia_detalhe or "")

    call_ok = Call(
        tabulacao_operador="EM NEGOCIAÇÃO",
        categoria="EM_NEGOCIACAO",
    )
    pipeline.calcular_divergencia(call_ok)
    assert call_ok.divergencia_tabulacao is False


def test_analyst_endpoints_and_filters(client):
    db = SessionLocal()
    c1 = Call(
        id_ligacao=99901,
        telefone="11999990001",
        nome_esperado="TESTE CLIENTE COMERCIAL",
        operador_nome="OPERADOR COMERCIAL",
        tipo_agente="COMERCIAL",
        tipo_discagem="ATIVO",
        tronco="4NET - BENCONSIG",
        desligado_por="CLIENTE",
        desligamento_detalhe="Atendimento: BYE recebido.",
        tabulacao_operador="CLIENTE NÃO TEM INTERESSE",
        categoria="EM_NEGOCIACAO",
        status="done",
        divergencia_tabulacao=True,
        data_ligacao=datetime(2026, 11, 6, 10, 0, 0),
    )
    c2 = Call(
        id_ligacao=99902,
        telefone="11999990002",
        nome_esperado="TESTE CLIENTE DIGITAL",
        operador_nome="OPERADOR VIRTUAL",
        tipo_agente="DIGITAL",
        tipo_discagem="URA",
        tronco="VENDITORE - URA",
        desligado_por="OPERADOR",
        desligamento_detalhe="Atendimento: BYE enviado.",
        tabulacao_operador="LIGAÇÃO MUDA / CAIXA POSTAL",
        categoria="LIGACAO_MUDA",
        status="done",
        divergencia_tabulacao=False,
        data_ligacao=datetime(2026, 11, 6, 11, 0, 0),
    )
    db.add_all([c1, c2])
    db.commit()
    db.close()

    # 1. Test analyst filter options
    r = client.get("/api/v1/analyst/filters-options")
    assert r.status_code == 200
    opts = r.json()
    assert "operadores" in opts
    assert "troncos" in opts
    assert "COMERCIAL" in opts["tipos_agente"]
    assert "CLIENTE" in opts["desligado_por"]

    # 2. Test filter by desligado_por
    r = client.get("/api/v1/calls?desligado_por=CLIENTE")
    assert r.status_code == 200
    items = r.json()["items"]
    assert any(i["id_ligacao"] == 99901 for i in items)
    assert not any(i["id_ligacao"] == 99902 for i in items)

    # 3. Test filter by tipo_agente
    r = client.get("/api/v1/calls?tipo_agente=DIGITAL")
    assert r.status_code == 200
    items = r.json()["items"]
    assert any(i["id_ligacao"] == 99902 for i in items)
    assert not any(i["id_ligacao"] == 99901 for i in items)

    # 4. Test filter by divergencia
    r = client.get("/api/v1/calls?divergencia=true")
    assert r.status_code == 200
    items = r.json()["items"]
    assert any(i["id_ligacao"] == 99901 for i in items)

    # 5. Test summary analytics
    r = client.get("/api/v1/analytics/summary")
    assert r.status_code == 200
    s = r.json()
    assert "desligamentos" in s
    assert "agentes" in s
    assert "discagens" in s
    assert "divergencias" in s
    assert "matriz_contraste" in s
    assert "ranking_operadores" in s

    # 6. Test CSV Export
    r = client.get("/api/v1/calls/export?tipo_agente=COMERCIAL")
    assert r.status_code == 200
    assert "text/csv" in r.headers["content-type"]
    assert len(r.content) > 50
