"""Monitoria, fase 3: o supervisor vê só a própria equipe, o levantamento e registra a ciência."""
import itertools
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import settings
from app.database import SessionLocal
from app.main import app
from app.models import Call, Usuario
from app.services import auth, avaliacoes, equipes

_ids = itertools.count(970000)
EQ_A, EQ_B = "EQUIPE SUP A", "EQUIPE SUP B"


def _usuario(email, papel, grupos=None) -> int:
    with SessionLocal() as db:
        u = db.scalars(select(Usuario).where(Usuario.email == email)).first()
        u = u or auth.criar_usuario(db, email, email.split("@")[0].title(), "senha-forte-1", papel)
        db.flush()
        if grupos is not None:
            equipes.definir(db, u.id, grupos)
        db.commit()
        return u.id


def _avaliada(grupo: str, operador: str, nota_erros: int = 0, critico=False, data=datetime(2025, 9, 3, 10)) -> tuple[int, int]:
    """Cria a ligação e a avaliação do script finalizada (pela API, sem login)."""
    with SessionLocal() as db:
        c = Call(id_ligacao=next(_ids), status="pendente_avaliacao", caminho_audio="/tmp/x.mp3", data_ligacao=data,
                 operador_nome=operador, grupo_origem=grupo, tabulacao_operador="CLIENTE NÃO TEM INTERESSE")
        db.add(c)
        db.commit()
        cid = c.id
    with TestClient(app) as cl:
        av = cl.post(f"/api/v1/calls/{cid}/avaliacao").json()
        desfecho = "venda" if critico else "recusa"
        secs = [s for s in av["script"]["secoes"] if avaliacoes.secao_aplica(s["aplicabilidade"], desfecho)]
        itens = [i for s in secs for i in s["itens"]]
        marc = [{"item_id": i["id"], "estado": "acertou"} for i in itens]
        for k in range(nota_erros):
            marc[k] = {"item_id": itens[k]["id"], "estado": "errou", "comentario": "errou"}
        if critico:
            idx = next(n for n, i in enumerate(itens) if i["critico"])
            marc[idx] = {"item_id": itens[idx]["id"], "estado": "errou", "comentario": "sem documento"}
        cl.put(f"/api/v1/avaliacoes/{av['id']}", json={"desfecho": desfecho, "categoria": "SEM_INTERESSE", "itens": marc,
                                                       "feedback_melhorar": "Treinar abertura"})
        r = cl.post(f"/api/v1/avaliacoes/{av['id']}/finalizar")
        assert r.status_code == 200, r.text
        return cid, av["id"]


@pytest.fixture(scope="module")
def dados():
    a1 = _avaliada(EQ_A, "Op Sup A1", nota_erros=2)
    a2 = _avaliada(EQ_A, "Op Sup A2", critico=True, data=datetime(2025, 9, 10, 10))
    b1 = _avaliada(EQ_B, "Op Sup B1")
    return {"a1": a1, "a2": a2, "b1": b1}


@pytest.fixture
def com_login(monkeypatch):
    monkeypatch.setattr(settings, "auth_ativo", True)
    with TestClient(app) as c:
        yield c


def _entrar(c, email):
    c.cookies.clear()
    assert c.post("/api/v1/auth/login", json={"email": email, "senha": "senha-forte-1"}).status_code == 200


def test_supervisor_ve_so_a_propria_equipe(com_login, dados):
    _usuario("sup.a@x.com", "supervisor", [EQ_A])
    _entrar(com_login, "sup.a@x.com")
    (cid_a, aid_a), (cid_b, aid_b) = dados["a1"], dados["b1"]
    assert com_login.get(f"/api/v1/calls/{cid_a}").status_code == 200
    assert com_login.get(f"/api/v1/calls/{cid_b}").status_code == 404, "ligação de outra equipe nem aparece"
    assert com_login.get(f"/api/v1/calls/{cid_b}/audio").status_code == 404
    assert com_login.get(f"/api/v1/avaliacoes/{aid_b}").status_code == 404
    lista = com_login.get("/api/v1/calls", params={"page_size": 500}).json()["items"]
    assert lista and {c["grupo_origem"] for c in lista} == {EQ_A}
    assert all(c["operador_nome"] != "Op Sup B1" for c in lista)
    resumo = com_login.get("/api/v1/analytics/summary").json()
    assert all(r["operador"] != "Op Sup B1" for r in resumo["ranking_operadores"])
    ops = com_login.get("/api/v1/analyst/filters-options").json()
    assert {g["nome"] for g in ops["grupos"]} == {EQ_A}
    sup = com_login.get("/api/v1/supervisao/resumo").json()
    assert {o["operador"] for o in sup["operadores"]} == {"Op Sup A1", "Op Sup A2"}
    assert sup["escopo"] == {"restrito": True, "grupos": [EQ_A]}
    assert "Op Sup B1" not in com_login.get("/api/v1/supervisao/exportar").text
    assert "Op Sup B1" not in com_login.get("/api/v1/calls/export").text


def test_supervisor_sem_equipe_nao_ve_nada(com_login, dados):
    _usuario("sup.sem@x.com", "supervisor", [])
    _entrar(com_login, "sup.sem@x.com")
    assert com_login.get("/api/v1/calls").json()["total"] == 0
    r = com_login.get("/api/v1/supervisao/resumo").json()
    assert r["avaliacoes"] == 0 and r["escopo"]["grupos"] == []


def test_admin_e_monitora_veem_todas_as_equipes(com_login, dados):
    for email, papel in (("adm.sup@x.com", "admin"), ("mon.sup@x.com", "monitora")):
        _usuario(email, papel)
        _entrar(com_login, email)
        ops = {o["operador"] for o in com_login.get("/api/v1/supervisao/resumo").json()["operadores"]}
        assert {"Op Sup A1", "Op Sup B1"} <= ops


def test_levantamento_nota_falha_critica_e_itens(client, dados):
    r = client.get("/api/v1/supervisao/resumo", params={"grupo": EQ_A}).json()
    assert r["avaliacoes"] == 2 and r["falhas_criticas"] == 1 and r["falha_critica_pct"] == 50.0
    a1 = next(o for o in r["operadores"] if o["operador"] == "Op Sup A1")
    assert a1["nota_media"] < 100 and a1["sem_ciencia"] == 1
    assert r["itens"] and r["itens"][0]["errou"] >= 1
    assert any(i["critico"] and i["errou"] for i in r["itens"])
    assert [e["avaliacoes"] for e in r["evolucao"]] == [1, 1], "duas semanas diferentes"
    lst = client.get("/api/v1/supervisao/avaliacoes", params={"grupo": EQ_A, "falha_critica": "true"}).json()
    assert lst["total"] == 1 and lst["itens"][0]["operador_nome"] == "Op Sup A2"
    assert lst["itens"][0]["feedback_melhorar"] == "Treinar abertura"


def test_ciencia_do_supervisor_e_reabertura(com_login, dados):
    _usuario("sup.a@x.com", "supervisor", [EQ_A])
    _entrar(com_login, "sup.a@x.com")
    _, aid = dados["a1"]
    _, aid_b = dados["b1"]
    assert com_login.post(f"/api/v1/avaliacoes/{aid_b}/ciencia", json={}).status_code == 404, "outra equipe"
    r = com_login.post(f"/api/v1/avaliacoes/{aid}/ciencia", json={"devolutiva": "Conversei no 1:1 de hoje"})
    assert r.status_code == 200 and r.json()["por"] == "Sup.A"
    assert com_login.get(f"/api/v1/avaliacoes/{aid}").json()["ciencia"]["devolutiva"] == "Conversei no 1:1 de hoje"
    pend = com_login.get("/api/v1/supervisao/avaliacoes", params={"ciencia": "pendente"}).json()
    assert aid not in [i["id"] for i in pend["itens"]]

    # a monitora reabre: a ciência sai (fica na auditoria) e o supervisor precisa ver de novo
    _usuario("mon.sup@x.com", "monitora")
    _entrar(com_login, "mon.sup@x.com")
    assert com_login.post(f"/api/v1/avaliacoes/{aid}/ciencia", json={}).status_code == 403, "monitora não dá ciência"
    r = com_login.post(f"/api/v1/avaliacoes/{aid}/reabrir", json={"motivo": "corrigir nota"}).json()
    assert r["eventos"][-1]["detalhe"]["antes"]["ciencia"]["por"] == "Sup.A"
    assert com_login.get(f"/api/v1/avaliacoes/{aid}").json()["ciencia"] is None
    com_login.post(f"/api/v1/avaliacoes/{aid}/finalizar")


def test_admin_vincula_equipes_do_supervisor(com_login, dados):
    uid = _usuario("sup.novo@x.com", "supervisor")
    mon = _usuario("mon.sup@x.com", "monitora")
    _usuario("adm.sup@x.com", "admin")
    _entrar(com_login, "adm.sup@x.com")
    r = com_login.put(f"/api/v1/usuarios/{uid}/grupos", json={"grupos": [EQ_B, " ", EQ_A, EQ_B]})
    assert r.json()["grupos"] == [EQ_A, EQ_B]
    assert com_login.put(f"/api/v1/usuarios/{mon}/grupos", json={"grupos": [EQ_A]}).status_code == 409
    eq = com_login.get("/api/v1/equipes").json()
    assert {EQ_A, EQ_B} <= {g["nome"] for g in eq["grupos"]}
    assert next(s for s in eq["supervisores"] if s["id"] == uid)["grupos"] == [EQ_A, EQ_B]
    _usuario("sup.a@x.com", "supervisor", [EQ_A])
    _entrar(com_login, "sup.a@x.com")
    assert com_login.get("/api/v1/equipes").status_code == 403
