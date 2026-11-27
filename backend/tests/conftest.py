import os
import tempfile

temp_dir = tempfile.mkdtemp()
db_path = os.path.join(temp_dir, "test.db").replace("\\", "/")
# TEST_DATABASE_URL permite rodar a mesma suíte contra PostgreSQL (o banco é zerado no início)
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{db_path}"
os.environ["ARGUS_TOKEN"] = ""
os.environ["AUTH_ATIVO"] = "false"  # os testes de login (test_auth.py) ligam por conta própria
os.environ["RECORDINGS_DIR"] = os.path.join(temp_dir, "gravacoes")

import pytest
from fastapi.testclient import TestClient

from app.database import init_db
from app.main import app


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    if os.environ.get("TEST_DATABASE_URL"):
        from sqlalchemy import text

        from app.database import engine

        with engine.begin() as conn:  # zera tudo, inclusive tabelas que saíram do código (ex.: da versão com IA)
            conn.execute(text("DROP SCHEMA public CASCADE"))
            conn.execute(text("CREATE SCHEMA public"))
    init_db()


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c
