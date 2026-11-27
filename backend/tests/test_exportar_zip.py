"""Exportação das gravações em .zip, dividido em Equipe / Operador / Cliente / Tabulação."""
import io
import itertools
import zipfile
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import settings
from app.database import SessionLocal
from app.main import app
from app.models import Call, Usuario
from app.services import auth, equipes, exportar_zip

_ids = itertools.count(980000)


def _call(tmp_path, audio=True, **kw) -> int:
    i = next(_ids)
    caminho = None
    if audio:
        caminho = tmp_path / f"{i}.mp3"
        caminho.write_bytes(b"ID3fake-mp3-" + str(i).encode())
    base = dict(id_ligacao=i, status="avaliada", caminho_audio=str(caminho) if caminho else None,
                data_ligacao=datetime(2025, 10, 6, 14, 30, 5), grupo_origem="EQUIPE ZIP", operador_nome="Op Zip",
                nome_esperado="Maria Zip", tabulacao_operador="CLIENTE NÃO TEM INTERESSE", telefone="11999990000")
    with SessionLocal() as db:
        c = Call(**{**base, **kw})
        db.add(c)
        db.commit()
        return c.id


def _zip(r) -> zipfile.ZipFile:
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/zip"
    return zipfile.ZipFile(io.BytesIO(r.content))


def test_pastas_por_equipe_operador_cliente_e_tabulacao(client, tmp_path):
    a = _call(tmp_path)
    b = _call(tmp_path, nome_esperado="João/Zip?", tabulacao_operador="MUDA: CAIXA POSTAL")
    sem = _call(tmp_path, audio=False)
    z = _zip(client.get("/api/v1/calls/gravacoes.zip", params={"ids": f"{a},{b},{sem}"}))
    nomes = z.namelist()
    with SessionLocal() as db:
        id_a = db.get(Call, a).id_ligacao
    assert f"EQUIPE ZIP/Op Zip/Maria Zip/CLIENTE NÃO TEM INTERESSE/2025-10-06_143005_lig{id_a}.mp3" in nomes
    assert any(n.startswith("EQUIPE ZIP/Op Zip/João Zip/MUDA CAIXA POSTAL/") for n in nomes), "sem / ? : no nome"
    assert z.read(nomes[0]).startswith(b"ID3fake")
    lista = z.read("lista_gravacoes.csv").decode("utf-8-sig")
    assert lista.count("\n") == 4 and "sem gravação no servidor" in lista
    assert len([n for n in nomes if n.endswith(".mp3")]) == 2


def test_usa_os_filtros_da_tela(client, tmp_path):
    _call(tmp_path, operador_nome="Op Filtro Zip", grupo_origem="EQUIPE FZ")
    _call(tmp_path, operador_nome="Outro Zip", grupo_origem="EQUIPE FZ")
    z = _zip(client.get("/api/v1/calls/gravacoes.zip", params={"operador": "Op Filtro Zip"}))
    mp3 = [n for n in z.namelist() if n.endswith(".mp3")]
    assert len(mp3) == 1 and mp3[0].startswith("EQUIPE FZ/Op Filtro Zip/")


def test_limite_e_filtro_vazio(client, tmp_path, monkeypatch):
    assert client.get("/api/v1/calls/gravacoes.zip", params={"operador": "Ninguém Zip"}).status_code == 404
    _call(tmp_path, operador_nome="Op Limite Zip")
    _call(tmp_path, operador_nome="Op Limite Zip")
    monkeypatch.setattr(settings, "zip_max_gravacoes", 1)
    r = client.get("/api/v1/calls/gravacoes.zip", params={"operador": "Op Limite Zip"})
    assert r.status_code == 413 and "limite" in r.json()["detail"]


def test_nome_de_pasta_seguro():
    assert exportar_zip.pasta('  a<b>c:"d|e?*  ', "x") == "a b c d e"
    assert exportar_zip.pasta(None, "Sem equipe") == "Sem equipe"
    assert exportar_zip.pasta("...", "Sem equipe") == "Sem equipe"
    assert len(exportar_zip.pasta("x" * 200, "p")) == 60


@pytest.fixture
def com_login(monkeypatch):
    monkeypatch.setattr(settings, "auth_ativo", True)
    with TestClient(app) as c:
        yield c


def _entrar(c, email, papel, grupos=None):
    with SessionLocal() as db:
        u = db.scalars(select(Usuario).where(Usuario.email == email)).first()
        u = u or auth.criar_usuario(db, email, "Pessoa Zip", "senha-forte-1", papel)
        db.flush()
        if grupos is not None:
            equipes.definir(db, u.id, grupos)
        db.commit()
    c.cookies.clear()
    assert c.post("/api/v1/auth/login", json={"email": email, "senha": "senha-forte-1"}).status_code == 200


def test_permissoes_e_equipe_do_supervisor(com_login, tmp_path):
    minha = _call(tmp_path, grupo_origem="EQUIPE ZIP SUP")
    outra = _call(tmp_path, grupo_origem="EQUIPE ZIP OUTRA")
    _entrar(com_login, "leitura.zip@x.com", "leitura")
    assert com_login.get("/api/v1/calls/gravacoes.zip", params={"ids": str(minha)}).status_code == 403
    _entrar(com_login, "monitora.zip@x.com", "monitora")
    assert com_login.get("/api/v1/calls/gravacoes.zip", params={"ids": f"{minha},{outra}"}).status_code == 200
    _entrar(com_login, "sup.zip@x.com", "supervisor", ["EQUIPE ZIP SUP"])
    z = _zip(com_login.get("/api/v1/calls/gravacoes.zip", params={"ids": f"{minha},{outra}"}))
    assert {n.split("/")[0] for n in z.namelist() if n.endswith(".mp3")} == {"EQUIPE ZIP SUP"}
