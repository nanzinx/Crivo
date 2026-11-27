"""Controle de ponto (fase 4): paridade com a planilha "Controle de Ponto - Argus" e regras de borda.

As fixtures vêm das abas Base e Relatório da planilha real, com os nomes trocados por pseudônimos (LGPD).
"""
import json
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.database import SessionLocal
from app.main import app
from app.models import Call, Operador, PontoGrupo, PontoImportacao, PontoJornada, PontoPausa
from app.services import ponto

FIX = Path(__file__).parent / "fixtures" / "ponto"
ESPERADO = json.loads((FIX / "esperado.json").read_text(encoding="utf-8"))


def _limpar():
    with SessionLocal() as db:
        for t in (PontoJornada, PontoPausa, PontoImportacao):
            db.query(t).delete()
        db.commit()


@pytest.fixture(scope="module")
def importado():
    _limpar()
    arquivos = [("arquivos", (n, (FIX / n).read_bytes(), "text/csv"))
                for n in ("entrada-saida-ontem.csv", "entrada-hoje.csv", "pausas-ontem.csv")]
    with TestClient(app) as c:  # os 3 de uma vez, como na planilha
        r = c.post("/api/v1/ponto/importar", files=arquivos).json()["arquivos"]
    return {a["arquivo"]: a for a in r}


def test_reconhece_cada_arquivo_sozinho(importado):
    assert (importado["entrada-saida-ontem.csv"]["tipo"], importado["entrada-saida-ontem.csv"]["data"]) == ("ponto", "2026-11-25")
    assert (importado["entrada-hoje.csv"]["tipo"], importado["entrada-hoje.csv"]["data"]) == ("ponto", "2026-11-26")
    assert (importado["pausas-ontem.csv"]["tipo"], importado["pausas-ontem.csv"]["data"]) == ("pausas", "2026-11-25")
    assert importado["pausas-ontem.csv"]["linhas"] == 3356 and all(a["erro"] is None for a in importado.values())


def _por_nome(linhas):
    return {l["operador"]: l for l in linhas}


def test_paridade_com_relatorio_ontem_da_planilha(client, importado):
    r = client.get("/api/v1/ponto/relatorio", params={"data": "2026-11-25"}).json()
    nosso, deles = _por_nome(r["linhas"]), _por_nome(ESPERADO["ontem"])
    assert set(nosso) == set(deles), "mesmos operadores (sem URA PORT, SEM SUPERVISOR e TESTE)"
    for nome, e in deles.items():
        n = nosso[nome]
        for campo in ("entrada_seg", "saida_seg", "jornada_seg", "almoco_inicio", "almoco_fim", "almoco_seg", "tmp_seg",
                      "qtp", "observacao"):
            assert n[campo] == e[campo], f"{nome} · {campo}: {n[campo]!r} != planilha {e[campo]!r}"
    assert [l["operador"] for l in r["linhas"]] == [l["operador"] for l in ESPERADO["ontem"]], "mesma ordem"
    assert r["resumo"]["atrasos"] == sum(1 for l in deles.values() if l["observacao"])


def test_paridade_com_relatorio_hoje_da_planilha(client, importado):
    r = client.get("/api/v1/ponto/relatorio", params={"data": "2026-11-26", "modo": "entrada"}).json()
    nosso, deles = _por_nome(r["linhas"]), _por_nome(ESPERADO["hoje"])
    assert set(nosso) == set(deles)
    for nome, e in deles.items():
        assert (nosso[nome]["entrada_seg"], nosso[nome]["observacao"]) == (e["entrada_seg"], e["observacao"]), nome
        assert nosso[nome]["saida_seg"] is None and nosso[nome]["tmp_seg"] is None
    assert r["resumo"]["atrasos"] == 2 and r["resumo"]["presentes"] == 27, "como no resumo da aba Início"


def test_reimportar_a_mesma_data_substitui(client, importado):
    arq = ("arquivos", ("de-novo.csv", (FIX / "entrada-saida-ontem.csv").read_bytes(), "text/csv"))
    r = client.post("/api/v1/ponto/importar", files=[arq]).json()["arquivos"][0]
    assert r["substituiu"] is True
    with SessionLocal() as db:
        assert db.query(PontoJornada).filter(PontoJornada.data == date(2026, 11, 25)).count() == r["linhas"]
        assert db.query(PontoImportacao).filter(PontoImportacao.tipo == "ponto",
                                                PontoImportacao.data_ref == date(2026, 11, 25)).count() == 1


def test_arquivo_que_nao_e_do_argus(client):
    r = client.post("/api/v1/ponto/importar", files=[("arquivos", ("x.csv", b"a;b\n1;2\n", "text/csv"))]).json()
    assert "não parece" in r["arquivos"][0]["erro"]


def test_equipe_do_ponto_preenche_as_ligacoes(client, importado):
    with SessionLocal() as db:
        o = db.get(Operador, ponto.chave("OPERADOR 001"))
        assert o is not None and o.grupo == "CAHUAN - COMERCIAL"
        c = Call(id_ligacao=991001, status="pendente_avaliacao", operador_nome="operador 001")
        db.add(c)
        db.commit()
        cid = c.id
    client.post("/api/v1/ponto/importar", files=[("arquivos", ("e.csv", (FIX / "entrada-hoje.csv").read_bytes(), "text/csv"))])
    with SessionLocal() as db:
        assert db.get(Call, cid).grupo_origem == "CAHUAN - COMERCIAL"
    # ligação nova que chega pelo Argus já entra com a equipe
    client.post("/api/v1/webhooks/argus", json={"idTipoWebhook": 1, "idLigacao": 991002, "nomeUsuario": "OPERADOR 001"})
    with SessionLocal() as db:
        assert db.scalars(select(Call).where(Call.id_ligacao == 991002)).one().grupo_origem == "CAHUAN - COMERCIAL"


# --------------------------------------------------------------------------- regras de borda
def _grupo(entrada, tol=10):
    return PontoGrupo(grupo="X", incluir=True, entrada_prevista=entrada, tolerancia_min=tol)


@pytest.mark.parametrize("prevista,entrada,atraso", [
    ("10:00", "10:10", 0),  # igual à tolerância não é atraso
    ("10:00", "10:11", 11),
    ("10:00", "09:40", 0),  # entrada antecipada
    ("08:30;14:00", "14:16", 16),  # turno da tarde: compara com o mais próximo
    ("08:30;14:00", "08:50", 20),
    ("", "11:00", 0),  # sem horário previsto
    ("10:00", None, 0),  # sem entrada
])
def test_atraso(prevista, entrada, atraso):
    assert ponto.minutos_atraso(_grupo(prevista), ponto.hora_seg(entrada)) == atraso


def test_almoco_fracionado_pausa_sem_fim_e_grupo_novo(client):
    _limpar()
    pontos = ('"Data";"Grupo Atual";"Operador";"Entrada";"Saída"\r\n'
              '"2026-12-01";"EQUIPE NOVA";"ANA BORDA";"10:05";"17:00"\r\n'
              '"2026-12-01";"EQUIPE NOVA";"ANA BORDA";"09:58";""\r\n'  # duas linhas: vale a entrada mais cedo
              '"2026-12-01";"URA PORT - 9";"OPER VIRTUAL 99";"08:00";"18:00"\r\n'
              '"2026-12-01";"EQUIPE NOVA";"BETO TESTE";"08:00";"18:00"\r\n'
              '"2026-12-01";"EQUIPE NOVA";"CARLA FALTOU";"";""\r\n').encode("cp1252")
    pausas = ('" ";"Grupo Operacional";"Operador";"Descrição da Pausa";"Inicio";"Fim";"Tempo"\r\n'
              '"";"EQUIPE NOVA";"ANA BORDA";"Almoço";"01/12/2026 12:00:00";"01/12/2026 12:20:00";"00:20:00"\r\n'
              '"";"EQUIPE NOVA";"ANA BORDA";"Almoço";"01/12/2026 13:00:00";"01/12/2026 13:40:00";"00:40:00"\r\n'
              '"";"EQUIPE NOVA";"ANA BORDA";"PAUSA NOVA";"01/12/2026 15:00:00";"";"00:05:00"\r\n'
              '"";"EQUIPE NOVA";"ANA BORDA";"Banheiro";"30/11/2026 23:55:00";"01/12/2026 00:05:00";"00:10:00"\r\n'
              '"";"EQUIPE NOVA";"FORA DO PONTO";"Banheiro";"01/12/2026 15:00:00";"01/12/2026 15:05:00";"00:05:00"\r\n'
              ).encode("cp1252")
    r = client.post("/api/v1/ponto/importar", files=[("arquivos", ("p.csv", pontos, "text/csv")),
                                                      ("arquivos", ("z.csv", pausas, "text/csv"))]).json()
    assert [a["erro"] for a in r["arquivos"]] == [None, None]
    rel = client.get("/api/v1/ponto/relatorio", params={"data": "2026-12-01"}).json()
    linhas = _por_nome(rel["linhas"])
    assert set(linhas) == {"ANA BORDA", "CARLA FALTOU"}, "URA PORT novo entra com NÃO; TESTE é ignorado"
    ana = linhas["ANA BORDA"]
    assert ana["entrada_seg"] == 9 * 3600 + 58 * 60 and ana["saida_seg"] == 17 * 3600
    assert ana["almoco_inicio"] == "2026-12-01T13:00:00" and ana["almoco_seg"] == 3600, "o mais longo; soma dos dois"
    assert ana["tmp_seg"] == 300 and ana["qtp"] == 1, "pausa nova conta; a que começou no dia anterior não"
    assert linhas["CARLA FALTOU"]["entrada_seg"] is None and linhas["CARLA FALTOU"]["tmp_seg"] is None
    cfg = client.get("/api/v1/ponto/config").json()
    novos = {g["grupo"]: g["incluir"] for g in cfg["grupos"]}
    assert novos["EQUIPE NOVA"] is True and novos["URA PORT - 9"] is False
    assert {p["descricao"]: p["conta"] for p in cfg["pausas"]}["PAUSA NOVA"] is True


def test_config_valida_horario_e_muda_o_relatorio(client):
    r = client.put("/api/v1/ponto/config", json={"grupos": [{"grupo": "EQUIPE NOVA", "incluir": True,
                                                            "entrada_prevista": "9h", "tolerancia_min": 10}]})
    assert r.status_code == 422
    client.put("/api/v1/ponto/config", json={"grupos": [{"grupo": "EQUIPE NOVA", "incluir": True,
                                                        "entrada_prevista": "09:30", "tolerancia_min": 5}]})
    ana = _por_nome(client.get("/api/v1/ponto/relatorio", params={"data": "2026-12-01"}).json()["linhas"])["ANA BORDA"]
    assert ana["observacao"] == "Atraso de 28 min"
