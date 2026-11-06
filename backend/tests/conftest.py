import os
import tempfile

temp_dir = tempfile.mkdtemp()
db_path = os.path.join(temp_dir, "test.db").replace("\\", "/")
os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
os.environ["OPENAI_API_KEY"] = ""

import pytest
from fastapi.testclient import TestClient

from app.database import init_db
from app.main import app


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    init_db()


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c
