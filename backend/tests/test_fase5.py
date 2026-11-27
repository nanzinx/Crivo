"""Monitoria, fase 5: alertas de monitoria e ponto (com equipe) e relatório diário com os blocos novos."""
import itertools
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import settings
from app.database import SessionLocal
from app.main import app
from app.models import Alerta, Avaliacao, Call, PontoImportacao, PontoJornada, PontoPausa, ScriptVersao, Usuario
from app.services import alertas, auth, equipes, notificacoes, relatorio

_ids = itertools.count(995000)
T = datetime(2026, 12, 10, 18, 0)


@pytest.fixture(autouse=True)
def sem_envio(monkeypatch):
    monkeypatch.setattr(notificacoes, "enviar", lambda *a, **k: {"enviado": False, "motivo": "teste"})


def _avaliacao(db, operador, grupo, nota, falha=False, quando=T - timedelta(hours=2)):
    v = db.scalars(select(ScriptVersao).where(ScriptVersao.status == "ativa")).first()
    c = Call(id_ligacao=next(_ids), status="avaliada", operador_nome=operador, grupo_origem=grupo, data_ligacao=quando,
             categoria="SEM_INTERESSE")
    db.add(c)
    db.flush()
    a = Avaliacao(call_id=c.id, status="finalizada", script_versao_id=v.id, nota=nota, falha_critica=falha,
                  categoria="SEM_INTERESSE", finalizada_em=quando + timedelta(minutes=30), monitora_nome="Monitora")
    db.add(a)
    db.flush()
    c.avaliacao_id = a.id


def test_alertas_de_nota_baixa_e_falha_critica(client):
    with SessionLocal() as db:
        for n in (40, 45, 48):
            _avaliacao(db, "Op Nota Baixa", "EQUIPE F5 A", n)
        _avaliacao(db, "Op Falha F5", "EQUIPE F5 B", 90, falha=True)
        _avaliacao(db, "Op Nota Boa", "EQUIPE F5 A", 95)
        _avaliacao(db, "Op Nota Boa", "EQUIPE F5 A", 92)
        _avaliacao(db, "Op Nota Boa", "EQUIPE F5 A", 88)
        db.commit()
        alertas.avaliar(db, T)
        abertos = {a.chave: a for a in db.scalars(select(Alerta).where(Alerta.resolvido_em.is_(None)))}
    nota = abertos["aderencia:Op Nota Baixa"]
    assert nota.nivel == "critico" and nota.grupo == "EQUIPE F5 A" and "nota média 44" in nota.mensagem
    assert "aderencia:Op Nota Boa" not in abertos
    falha = abertos["falha_critica:Op Falha F5"]
    assert falha.nivel == "critico" and falha.grupo == "EQUIPE F5 B"
    regras = {r["tipo"] for r in client.get("/api/v1/alertas").json()["regras"]}
    assert {"aderencia", "falha_critica", "atraso", "almoco"} <= regras


def test_supervisor_ve_so_os_alertas_da_equipe_dele(monkeypatch):
    with SessionLocal() as db:
        u = db.scalars(select(Usuario).where(Usuario.email == "sup.f5@x.com")).first()
        u = u or auth.criar_usuario(db, "sup.f5@x.com", "Sup F5", "senha-forte-1", "supervisor")
        db.flush()
        equipes.definir(db, u.id, ["EQUIPE F5 B"])
        db.add(Alerta(chave="geral:f5", tipo="sistema", nivel="critico", titulo="Geral", mensagem="x", grupo=None))
        db.commit()
    monkeypatch.setattr(settings, "auth_ativo", True)
    with TestClient(app) as c:
        c.post("/api/v1/auth/login", json={"email": "sup.f5@x.com", "senha": "senha-forte-1"})
        chaves = {a["chave"] for a in c.get("/api/v1/alertas").json()["abertos"]}
    assert "falha_critica:Op Falha F5" in chaves and "geral:f5" in chaves
    assert "aderencia:Op Nota Baixa" not in chaves, "alerta de outra equipe não aparece"


def _ponto(db, dia, nome, entrada, grupo="EQUIPE F5 P"):
    imp = PontoImportacao(tipo="ponto", data_ref=dia, arquivo="t.csv")
    db.add(imp)
    db.flush()
    h, m = entrada.split(":")
    db.add(PontoJornada(importacao_id=imp.id, data=dia, grupo=grupo, operador=nome,
                        entrada_seg=int(h) * 3600 + int(m) * 60, saida_seg=17 * 3600))
    return imp


def test_alertas_de_atraso_recorrente_e_almoco_longo(client):
    client.put("/api/v1/ponto/config", json={"grupos": [{"grupo": "EQUIPE F5 P", "incluir": True,
                                                        "entrada_prevista": "10:00", "tolerancia_min": 10}]})
    with SessionLocal() as db:
        for i, d in enumerate((date(2026, 12, 8), date(2026, 12, 9), date(2026, 12, 10))):
            _ponto(db, d, "ATRASADO F5", "10:25")
            _ponto(db, d, "PONTUAL F5", "09:58")
        imp = PontoImportacao(tipo="pausas", data_ref=date(2026, 12, 10), arquivo="p.csv")
        db.add(imp)
        db.flush()
        db.add(PontoPausa(importacao_id=imp.id, data=date(2026, 12, 10), grupo="EQUIPE F5 P", operador="PONTUAL F5",
                          descricao="Almoço", inicio=datetime(2026, 12, 10, 12), fim=datetime(2026, 12, 10, 13, 20),
                          segundos=80 * 60))
        db.commit()
        alertas.avaliar(db, T)
        abertos = {a.chave: a for a in db.scalars(select(Alerta).where(Alerta.resolvido_em.is_(None)))}
    atraso = abertos["atraso:ATRASADO F5"]
    assert atraso.grupo == "EQUIPE F5 P" and "3 atrasos" in atraso.mensagem and "75 min" in atraso.mensagem
    assert "atraso:PONTUAL F5" not in abertos
    almoco = abertos["almoco:EQUIPE F5 P:2026-12-10"]
    assert "PONTUAL F5 (80 min)" in almoco.mensagem


def test_relatorio_diario_tem_monitoria_e_ponto():
    with SessionLocal() as db:
        rel = relatorio.gerar(db, date(2026, 12, 10))
        m, p = rel.dados["monitoria"], rel.dados["ponto"]
        assert m["avaliacoes"] >= 7 and m["falhas_criticas"] >= 1 and m["nota_media"] is not None
        assert p["atrasos"] >= 1 and p["completo"] is True and p["almoco_acima_1h"] >= 1
        assert {"operador": "ATRASADO F5", "minutos": 25} in p["atrasados"]
        assert "🎧 Script:" in rel.texto and "🕘 Ponto:" in rel.texto and "ATRASADO F5: 25 min" in rel.texto
        h = relatorio.html(rel)
        assert "Monitoria do script" in h and "Ponto" in h and "ATRASADO F5" in h


def test_pagina_do_operador_e_painel(client):
    r = client.get("/api/v1/operadores/Op Nota Baixa/resumo", params={"dias": 3650}).json()
    assert r["equipe"] == "EQUIPE F5 A" and r["monitoria"]["avaliacoes"] == 3
    assert r["monitoria"]["nota_media"] == 44.3 and len(r["monitoria"]["notas"]) == 3
    p = client.get("/api/v1/operadores/ATRASADO F5/resumo").json()
    assert p["ponto"]["atrasos"] == 3 and p["ponto"]["dias"][0]["data"] == "2026-12-10"
    assert client.get("/api/v1/operadores/Ninguem F5/resumo").status_code == 404
    painel = client.get("/api/v1/painel").json()
    assert {"avaliadas_hoje", "aguardando", "nota_media_7d", "falhas_criticas_7d", "sem_ciencia"} <= set(painel["monitoria"])
    assert painel["ponto"] is not None and "atrasos" in painel["ponto"]


def test_supervisor_nao_abre_operador_de_outra_equipe(monkeypatch):
    monkeypatch.setattr(settings, "auth_ativo", True)
    with TestClient(app) as c:
        c.post("/api/v1/auth/login", json={"email": "sup.f5@x.com", "senha": "senha-forte-1"})
        assert c.get("/api/v1/operadores/Op Nota Baixa/resumo", params={"dias": 3650}).status_code == 404
        assert c.get("/api/v1/operadores/Op Falha F5/resumo", params={"dias": 3650}).status_code == 200
