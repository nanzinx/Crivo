"""Integração com a API do Argus para operadores/equipes e ponto (respostas simuladas, formato do manual)."""
from datetime import date, datetime

import pytest
from sqlalchemy import select

from app.database import SessionLocal
from app.models import Call, Operador, PontoJornada
from app.services import argus_client, argus_operacao, ponto

USUARIOS = [  # formato de /cmd/listarusuarios (doc-api-argus, 4.3)
    {"idUsuario": 501, "nome": "MARIA API SOUZA", "login": "maria", "ramal": "7001", "ativo": True, "idTipoUsuario": 2,
     "campanhas": [{"idCampanha": 12, "campanhaDesc": "PORT", "idGrupoUsuario": 3, "grupoUsuarioDesc": "EQUIPE API A",
                    "idUsuarioSupervisor": 90, "nomeUsuarioSupervisor": "SUPERVISORA API"}]},
    {"idUsuario": 502, "nome": "JOSÉ API LIMA", "login": "jose", "ramal": "7002", "ativo": False, "idTipoUsuario": 2,
     "campanhas": [{"idCampanha": 12, "idGrupoUsuario": 4, "grupoUsuarioDesc": "EQUIPE API B"}]},
]


@pytest.fixture
def argus(monkeypatch):
    monkeypatch.setattr(argus_client, "listar_usuarios", lambda **k: USUARIOS)
    monkeypatch.setattr(argus_client, "campaign_ids", lambda: [12])
    return monkeypatch


def test_sincroniza_operadores_equipe_e_supervisor(client, argus):
    with SessionLocal() as db:
        c = Call(id_ligacao=997001, status="pendente_avaliacao", operador_nome="Maria Api Souza")
        db.add(c)
        db.commit()
        cid = c.id
    r = client.post("/api/v1/sync/operadores").json()
    assert r["operadores"] == 2 and r["inativos"] == 1 and r["ligacoes_com_equipe"] >= 1
    with SessionLocal() as db:
        m = db.get(Operador, ponto.chave("MARIA API SOUZA"))
        assert (m.grupo, m.ramal, m.supervisor_argus, m.origem) == ("EQUIPE API A", "7001", "SUPERVISORA API", "argus")
        assert db.get(Call, cid).grupo_origem == "EQUIPE API A"
    eq = client.get("/api/v1/equipes").json()
    assert {"nome": "EQUIPE API A", "ligacoes": 1, "supervisores_argus": ["SUPERVISORA API"]} in eq["grupos"]


def test_webhook_acha_a_equipe_pelo_ramal(client, argus):
    client.post("/api/v1/sync/operadores")
    client.post("/api/v1/webhooks/argus", json={"idTipoWebhook": 1, "idLigacao": 997002, "codUsuarioIntegracao": "7002",
                                                "nomeUsuario": "Outro Nome no Discador"})
    with SessionLocal() as db:
        assert db.scalars(select(Call).where(Call.id_ligacao == 997002)).one().grupo_origem == "EQUIPE API B"


def test_falha_da_api_vira_erro_e_aparece_na_saude(client, monkeypatch):
    def _falha(**k):
        raise argus_client.ArgusError("Token inválido")
    monkeypatch.setattr(argus_client, "listar_usuarios", _falha)
    r = client.post("/api/v1/sync/operadores")
    assert r.status_code == 400 and "Token inválido" in r.json()["detail"]
    ev = client.get("/api/v1/saude").json()["eventos"]["argus_operadores"]
    assert ev["ok"] is False and ev["nome"] == "Operadores e equipes (API Argus)"


# --------------------------------------------------------------------------- ponto pela API
ENTRADAS = [{"data": "2026-12-15", "grupoAtual": "EQUIPE API A", "nomeUsuario": "MARIA API SOUZA",
             "entrada": "2026-12-15 10:14:00", "saida": "2026-12-15 17:01:00"},
            {"data": "2026-12-15", "grupoAtual": "EQUIPE API A", "nomeUsuario": "MARIA API SOUZA",
             "entrada": "2026-12-15 09:58:00", "saida": ""}]
PAUSAS = [{"grupoOperacional": "EQUIPE API A", "operador": "MARIA API SOUZA", "descricaoPausa": "Almoço",
           "inicio": "2026-12-15T12:00:00", "fim": "2026-12-15T12:50:00", "tempo": 3000},
          {"grupoOperacional": "EQUIPE API A", "operador": "MARIA API SOUZA", "descricaoPausa": "Banheiro",
           "inicio": "2026-12-15 15:00:00", "fim": "2026-12-15 15:04:00", "tempo": "00:04:00"}]


def test_ponto_pela_api_usa_as_mesmas_regras(client, monkeypatch):
    monkeypatch.setattr(argus_client, "entradas_saidas", lambda inicio, fim: iter(ENTRADAS))
    monkeypatch.setattr(argus_client, "pausas_detalhadas", lambda inicio, fim: iter(PAUSAS))
    client.put("/api/v1/ponto/config", json={"grupos": [{"grupo": "EQUIPE API A", "incluir": True,
                                                        "entrada_prevista": "10:00", "tolerancia_min": 10}]})
    r = client.post("/api/v1/sync/ponto", params={"data": "2026-12-15"}).json()
    assert r["ponto"] == {"linhas": 2, "erro": None} and r["pausas"] == {"linhas": 2, "erro": None}
    linha = {l["operador"]: l for l in client.get("/api/v1/ponto/relatorio", params={"data": "2026-12-15"}).json()["linhas"]}
    m = linha["MARIA API SOUZA"]
    assert m["entrada_seg"] == 9 * 3600 + 58 * 60 and m["saida_seg"] == 17 * 3600 + 60, "entrada mais cedo, saída mais tarde"
    assert m["almoco_seg"] == 3000 and m["tmp_seg"] == 240 and m["qtp"] == 1 and m["observacao"] is None


def test_formato_inesperado_mostra_os_campos_recebidos(client, monkeypatch):
    monkeypatch.setattr(argus_client, "entradas_saidas", lambda inicio, fim: iter([{"xpto": 1, "abc": "2"}]))
    monkeypatch.setattr(argus_client, "pausas_detalhadas", lambda inicio, fim: iter([]))
    r = client.post("/api/v1/sync/ponto", params={"data": "2026-12-16"})
    assert r.status_code == 400 and "Campos recebidos: abc, xpto" in r.json()["detail"]
    with SessionLocal() as db:
        assert not db.scalars(select(PontoJornada).where(PontoJornada.data == date(2026, 12, 16))).first()


def test_ciclo_importa_hoje_e_ontem_fechado(monkeypatch):
    chamados = []
    monkeypatch.setattr(argus_client, "listar_usuarios", lambda **k: USUARIOS)
    monkeypatch.setattr(argus_client, "entradas_saidas", lambda inicio, fim: chamados.append(inicio.date()) or iter([]))
    monkeypatch.setattr(argus_client, "pausas_detalhadas", lambda inicio, fim: iter([]))
    with SessionLocal() as db:
        argus_operacao.ciclo(db, datetime(2026, 12, 20, 9, 0))
    assert chamados == [date(2026, 12, 20), date(2026, 12, 19)]
