"""Login, perfis de acesso e gestão de usuários."""
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.database import SessionLocal
from app.main import app
from app.models import Call, Sessao, Usuario
from app.services import auth


@pytest.fixture
def com_login(monkeypatch):
    """Liga o login e começa sem nenhum usuário cadastrado."""
    monkeypatch.setattr(settings, "auth_ativo", True)
    with SessionLocal() as db:
        db.query(Sessao).delete()
        db.query(Usuario).delete()
        db.commit()
    with TestClient(app) as c:
        yield c


def _criar(email, papel, senha="senha-forte-1", nome=None):
    with SessionLocal() as db:
        u = auth.criar_usuario(db, email, nome or email.split("@")[0].title(), senha, papel)
        db.commit()
        return u.id


def _login(c, email, senha="senha-forte-1"):
    return c.post("/api/v1/auth/login", json={"email": email, "senha": senha})


# --------------------------------------------------------------------------- senhas e sessões
def test_senha_e_guardada_com_hash_e_sal():
    h1, h2 = auth.hash_senha("minha-senha-123"), auth.hash_senha("minha-senha-123")
    assert h1 != h2 and "minha-senha" not in h1 and h1.startswith("scrypt$")
    assert auth.verificar_senha("minha-senha-123", h1) and not auth.verificar_senha("outra", h1)


def test_sem_login_a_api_recusa(com_login):
    assert com_login.get("/api/v1/calls").status_code == 401
    assert com_login.get("/api/v1/analytics/summary").status_code == 401
    assert com_login.get("/health").status_code == 200, "health continua aberto (monitoramento externo)"
    assert com_login.get("/api/v1/auth/estado").json() == {"auth_ativo": True, "precisa_configurar": True, "usuario": None}


def test_primeiro_acesso_cria_o_administrador_uma_unica_vez(com_login):
    r = com_login.post("/api/v1/auth/primeiro-acesso", json={"email": "Chefe@Empresa.com", "nome": "Chefe", "senha": "senha-forte-1"})
    assert r.status_code == 200 and r.json()["papel"] == "admin" and r.json()["email"] == "chefe@empresa.com"
    assert "crivo_sessao" in r.cookies or com_login.cookies.get("crivo_sessao")
    assert com_login.get("/api/v1/calls").status_code == 200, "já entra logado"
    r2 = com_login.post("/api/v1/auth/primeiro-acesso", json={"email": "intruso@x.com", "nome": "X", "senha": "senha-forte-1"})
    assert r2.status_code == 409


def test_login_logout_e_sessao(com_login):
    _criar("ana@empresa.com", "supervisor")
    assert _login(com_login, "ana@empresa.com", "errada").status_code == 401
    r = _login(com_login, "ANA@empresa.com ")
    assert r.status_code == 200 and r.json()["nome"] == "Ana"
    assert com_login.get("/api/v1/auth/eu").json()["email"] == "ana@empresa.com"
    with SessionLocal() as db:
        s = db.query(Sessao).one()
        assert s.token_hash != com_login.cookies.get("crivo_sessao"), "o banco guarda só o hash do token"
    com_login.post("/api/v1/auth/logout")
    assert com_login.get("/api/v1/calls").status_code == 401


def test_token_bearer_para_scripts(com_login):
    _criar("bot@empresa.com", "leitura")
    token = _login(com_login, "bot@empresa.com").json()["token"]
    com_login.cookies.clear()
    assert com_login.get("/api/v1/calls", headers={"Authorization": f"Bearer {token}"}).status_code == 200


def test_bloqueio_apos_tentativas_erradas(com_login):
    _criar("bia@empresa.com", "supervisor")
    for _ in range(5):
        assert _login(com_login, "bia@empresa.com", "errada").status_code == 401
    r = _login(com_login, "bia@empresa.com")  # senha certa, mas bloqueada
    assert r.status_code == 429 and "minutos" in r.json()["detail"]


def test_usuario_inativo_nao_entra_e_perde_a_sessao(com_login):
    uid = _criar("caio@empresa.com", "supervisor")
    _login(com_login, "caio@empresa.com")
    with SessionLocal() as db:
        db.get(Usuario, uid).ativo = False
        db.commit()
    assert com_login.get("/api/v1/calls").status_code == 401
    assert _login(com_login, "caio@empresa.com").status_code == 401


# --------------------------------------------------------------------------- perfis
def test_perfil_leitura_so_consulta(com_login):
    _criar("leo@empresa.com", "leitura")
    _login(com_login, "leo@empresa.com")
    assert com_login.get("/api/v1/calls").status_code == 200
    r = com_login.post("/api/v1/sync/process")
    assert r.status_code == 403 and "leitura" in r.json()["detail"]
    assert com_login.get("/api/v1/usuarios").status_code == 403


def test_supervisor_revisa_com_o_proprio_nome(com_login):
    _criar("sara@empresa.com", "supervisor", nome="Sara Lima")
    _login(com_login, "sara@empresa.com")
    with SessionLocal() as db:
        c = Call(id_ligacao=910001, status="done", categoria="SEM_INTERESSE", categoria_ia="SEM_INTERESSE",
                 motor="openai", confianca=0.9, data_ligacao=datetime(2025, 9, 1, 9))
        db.add(c)
        db.commit()
    r = com_login.post(f"/api/v1/calls/{c.id}/revisao", json={"categoria": "SEM_INTERESSE", "revisor": "Outra Pessoa"})
    assert r.status_code == 200 and r.json()["revisado_por"] == "Sara Lima", "logado, vale o nome da sessão"
    assert com_login.get("/api/v1/usuarios").status_code == 403, "só administrador gerencia usuários"


# --------------------------------------------------------------------------- gestão de usuários
def test_admin_gerencia_usuarios(com_login):
    _criar("adm@empresa.com", "admin")
    _login(com_login, "adm@empresa.com")
    r = com_login.post("/api/v1/usuarios", json={"email": "novo@empresa.com", "nome": "Novo", "papel": "supervisor",
                                                 "senha": "provisoria-123"})
    assert r.status_code == 200, r.text
    uid = r.json()["id"]
    assert com_login.post("/api/v1/usuarios", json={"email": "novo@empresa.com", "nome": "X", "papel": "leitura",
                                                    "senha": "provisoria-123"}).status_code == 409
    assert com_login.post("/api/v1/usuarios", json={"email": "curta@empresa.com", "nome": "X", "papel": "leitura",
                                                    "senha": "123"}).status_code == 422
    assert com_login.patch(f"/api/v1/usuarios/{uid}", json={"papel": "leitura", "ativo": False}).json()["ativo"] is False
    lista = com_login.get("/api/v1/usuarios").json()
    assert {u["email"] for u in lista} == {"adm@empresa.com", "novo@empresa.com"}
    assert all("senha" not in str(u.keys()) for u in lista)


def test_nao_da_para_ficar_sem_administrador(com_login):
    uid = _criar("unico@empresa.com", "admin")
    _login(com_login, "unico@empresa.com")
    assert com_login.patch(f"/api/v1/usuarios/{uid}", json={"papel": "supervisor"}).status_code == 409
    assert com_login.patch(f"/api/v1/usuarios/{uid}", json={"ativo": False}).status_code == 409


def test_trocar_a_propria_senha(com_login):
    _criar("dani@empresa.com", "supervisor")
    _login(com_login, "dani@empresa.com")
    assert com_login.post("/api/v1/auth/senha", json={"atual": "errada", "nova": "nova-senha-123"}).status_code == 403
    assert com_login.post("/api/v1/auth/senha", json={"atual": "senha-forte-1", "nova": "nova-senha-123"}).status_code == 200
    com_login.post("/api/v1/auth/logout")
    assert _login(com_login, "dani@empresa.com", "nova-senha-123").status_code == 200


def test_webhook_do_argus_nao_exige_login(com_login):
    """O Argus não faz login: o webhook continua protegido só pelo segredo."""
    r = com_login.post("/api/v1/webhooks/argus", json={"idTipoWebhook": 1, "idLigacao": 920001})
    assert r.status_code == 200
