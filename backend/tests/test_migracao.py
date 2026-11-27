"""Migração do banco da versão com IA para a monitoria humana (idempotente, sem perder dados)."""
import os
import tempfile
from datetime import datetime

import pytest
from sqlalchemy import create_engine, text

from app.database import init_db

ESQUEMA = "migracao_teste"

CALLS_ANTIGA = """
CREATE TABLE calls (
    id INTEGER PRIMARY KEY, id_ligacao INTEGER UNIQUE, origem VARCHAR(20), status VARCHAR(20),
    telefone VARCHAR(20), nome_esperado VARCHAR(255), operador_nome VARCHAR(255),
    tabulacao_operador VARCHAR(255), caminho_audio TEXT, data_ligacao TIMESTAMP,
    categoria VARCHAR(40), subcategoria VARCHAR(60), confianca FLOAT, motor VARCHAR(30), resumo TEXT,
    transcricao TEXT, categoria_ia VARCHAR(40), subcategoria_ia VARCHAR(60),
    categoria_revisada VARCHAR(40), subcategoria_revisada VARCHAR(60), revisado_por VARCHAR(80),
    revisado_em TIMESTAMP, revisao_observacao TEXT, precisa_revisao BOOLEAN, revisao_motivo VARCHAR(255),
    na_amostra BOOLEAN, divergencia_tabulacao BOOLEAN, divergencia_detalhe TEXT, divergencia_gravidade VARCHAR(10),
    pediu_nao_ligar BOOLEAN, conflito_identidade BOOLEAN, custo_usd FLOAT, erro TEXT, criado_em TIMESTAMP
)"""
IA_USO_ANTIGA = """
CREATE TABLE ia_uso (id INTEGER PRIMARY KEY, call_id INTEGER REFERENCES calls(id), em TIMESTAMP,
                     tipo VARCHAR(20), modelo VARCHAR(64), custo_usd FLOAT)"""

T = datetime(2026, 11, 20, 10)
T_SQL = T.isoformat(sep=" ")  # texto: funciona igual no SQLite e no PostgreSQL
# (id, status, categoria, subcategoria, categoria_ia, categoria_revisada, subcategoria_revisada, revisado_por,
#  revisado_em, divergencia, gravidade, pediu_nao_ligar, caminho_audio, erro)
LINHAS = [
    (1, "done", "EM_NEGOCIACAO", "PROPOSTA_EM_ANDAMENTO", "SEM_INTERESSE", "EM_NEGOCIACAO", "PROPOSTA_EM_ANDAMENTO",
     "Ana Revisora", T, True, "alta", False, "/a/1.mp3", None),
    (2, "done", "SEM_INTERESSE", "CLIENTE_CALMO", "SEM_INTERESSE", None, None, None, None, True, "alta", True,
     "/a/2.mp3", None),
    (3, "awaiting_ai", None, None, None, None, None, None, None, False, None, False, "/a/3.mp3",
     "Configure OPENAI_API_KEY"),
    (4, "error", None, None, None, None, None, None, None, False, None, False, None, "download: 404"),
    (5, "error", None, None, None, None, None, None, None, False, None, False, "/a/5.mp3", "429 rate limit"),
    (6, "pending", None, None, None, None, None, None, None, False, None, False, None, None),
    (7, "pending", None, None, None, None, None, None, None, False, None, False, "/a/7.mp3", None),
]


@pytest.fixture
def banco_antigo():
    url = os.environ.get("TEST_DATABASE_URL")
    if url:
        with create_engine(url).begin() as conn:
            conn.execute(text(f"DROP SCHEMA IF EXISTS {ESQUEMA} CASCADE"))
            conn.execute(text(f"CREATE SCHEMA {ESQUEMA}"))
        eng = create_engine(url, connect_args={"options": f"-csearch_path={ESQUEMA}"})
    else:
        eng = create_engine(f"sqlite:///{os.path.join(tempfile.mkdtemp(), 'antigo.db')}")
    with eng.begin() as conn:
        conn.execute(text(CALLS_ANTIGA))
        conn.execute(text(IA_USO_ANTIGA))
        for (i, st, cat, sub, cat_ia, cat_rev, sub_rev, por, em, div, grav, nl, audio, erro) in LINHAS:
            conn.execute(text(
                "INSERT INTO calls (id, id_ligacao, origem, status, tabulacao_operador, categoria, subcategoria, "
                "confianca, motor, resumo, transcricao, categoria_ia, subcategoria_ia, categoria_revisada, "
                "subcategoria_revisada, revisado_por, revisado_em, precisa_revisao, revisao_motivo, na_amostra, "
                "divergencia_tabulacao, divergencia_gravidade, divergencia_detalhe, pediu_nao_ligar, "
                "conflito_identidade, custo_usd, caminho_audio, erro, criado_em, data_ligacao) VALUES "
                "(:i, :lig, 'argus', :st, 'CLIENTE NÃO TEM INTERESSE', :cat, :sub, 0.9, 'openai', 'resumo da IA', "
                "'alô, transcrição', :cat_ia, :sub, :cat_rev, :sub_rev, :por, :em, :rev, :motivo, :amostra, :div, "
                ":grav, :det, :nl, :conf, 0.002, :audio, :erro, :t, :t)"),
                dict(i=i, lig=990000 + i, st=st, cat=cat, sub=sub, cat_ia=cat_ia, cat_rev=cat_rev, sub_rev=sub_rev,
                     por=por, em=em and T_SQL, rev=i == 2, motivo="confiança baixa" if i == 2 else None, amostra=i == 2,
                     div=div, grav=grav, det="detalhe antigo" if div else None, nl=nl, conf=False, audio=audio,
                     erro=erro, t=T_SQL))
        conn.execute(text("INSERT INTO ia_uso (id, call_id, em, tipo, modelo, custo_usd) "
                          "VALUES (1, 2, :t, 'transcricao', 'modelo-antigo', 0.002)"), {"t": T_SQL})
    yield eng
    eng.dispose()
    if url:
        with create_engine(url).begin() as conn:
            conn.execute(text(f"DROP SCHEMA IF EXISTS {ESQUEMA} CASCADE"))


def _estado(eng) -> dict:
    with eng.connect() as conn:
        calls = {r.id: r for r in conn.execute(text(
            "SELECT id, status, categoria, subcategoria, divergencia_tabulacao, divergencia_gravidade, "
            "pediu_nao_ligar, erro, avaliacao_id, confianca, transcricao, categoria_ia, precisa_revisao "
            "FROM calls ORDER BY id"))}
        avals = conn.execute(text("SELECT id, call_id, status, origem, categoria, subcategoria, monitora_nome, "
                                  "finalizada_em FROM avaliacoes ORDER BY id")).all()
        ia_uso = conn.execute(text("SELECT COUNT(*) FROM ia_uso")).scalar()
        migracoes = [r[0] for r in conn.execute(text("SELECT nome FROM schema_migracoes"))]
    return {"calls": calls, "avals": avals, "ia_uso": ia_uso, "migracoes": migracoes}


def test_migracao_do_banco_com_ia(banco_antigo):
    init_db(banco_antigo)
    e = _estado(banco_antigo)
    c = e["calls"]

    # revisada por humano: vira avaliada, com uma avaliação "migrada" com o resultado da revisão
    assert c[1].status == "avaliada" and (c[1].categoria, c[1].subcategoria) == ("EM_NEGOCIACAO", "PROPOSTA_EM_ANDAMENTO")
    assert len(e["avals"]) == 1
    a = e["avals"][0]
    assert (a.call_id, a.status, a.origem, a.categoria, a.monitora_nome) == (
        1, "finalizada", "migrada", "EM_NEGOCIACAO", "Ana Revisora")
    assert c[1].avaliacao_id == a.id and a.finalizada_em is not None
    assert c[1].divergencia_tabulacao and c[1].divergencia_gravidade == "alta", "divergência recalculada"

    # só a IA tinha decidido: volta para a fila, sem resultado nem divergência
    for i in (2, 3, 5):
        assert c[i].status == "pendente_avaliacao", i
        assert c[i].categoria is None and c[i].subcategoria is None, i
        assert not c[i].divergencia_tabulacao and c[i].divergencia_gravidade is None, i
        assert not c[i].pediu_nao_ligar and not c[i].precisa_revisao and c[i].erro is None, i
        assert c[i].avaliacao_id is None, i
    assert c[4].status == "erro" and c[4].erro == "download: 404"
    assert c[6].status == "pendente"
    assert c[7].status == "pendente_avaliacao", "já tem o áudio: só falta a monitora"

    # dados antigos de IA continuam no banco (ocultos), até alguém rodar scripts/limpar_dados_ia.py
    assert c[2].confianca == 0.9 and c[2].transcricao and c[2].categoria_ia == "SEM_INTERESSE"
    assert e["ia_uso"] == 1
    assert "001_monitoria_humana" in e["migracoes"]


def test_migracao_e_idempotente(banco_antigo):
    init_db(banco_antigo)
    antes = _estado(banco_antigo)
    init_db(banco_antigo)
    depois = _estado(banco_antigo)
    assert [tuple(r) for r in antes["avals"]] == [tuple(r) for r in depois["avals"]]
    assert {k: tuple(v) for k, v in antes["calls"].items()} == {k: tuple(v) for k, v in depois["calls"].items()}
    assert depois["migracoes"].count("001_monitoria_humana") == 1


def test_banco_novo_registra_a_migracao_sem_fazer_nada():
    eng = create_engine(f"sqlite:///{os.path.join(tempfile.mkdtemp(), 'novo.db')}")
    init_db(eng)
    init_db(eng)
    with eng.connect() as conn:
        assert [r[0] for r in conn.execute(text("SELECT nome FROM schema_migracoes"))] == ["001_monitoria_humana"]
        assert conn.execute(text("SELECT COUNT(*) FROM avaliacoes")).scalar() == 0
    eng.dispose()


def test_script_limpa_os_dados_de_ia_mantendo_as_avaliacoes(banco_antigo, monkeypatch):
    from scripts import limpar_dados_ia

    init_db(banco_antigo)
    monkeypatch.setattr(limpar_dados_ia, "engine", banco_antigo)
    r = limpar_dados_ia.levantar()
    assert r["ia_uso"] == 1 and r["ligacoes_com_dados"] == 7 and "transcricao" in r["colunas"]
    limpar_dados_ia.limpar()
    e = _estado(banco_antigo)
    assert e["ia_uso"] == 0
    assert all(c.confianca is None and c.transcricao is None and c.categoria_ia is None for c in e["calls"].values())
    assert e["calls"][1].status == "avaliada" and len(e["avals"]) == 1, "avaliações intactas"
    assert limpar_dados_ia.levantar()["ligacoes_com_dados"] == 0
