"""Login, sessão e gestão de usuários. Também define as dependências que protegem a API."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import Usuario, agora
from ..services import auth

COOKIE = "crivo_sessao"
router = APIRouter(prefix="/api/v1", tags=["auth"])


def _token(request: Request) -> str | None:
    h = request.headers.get("authorization", "")
    if h.lower().startswith("bearer "):
        return h[7:].strip()
    return request.cookies.get(COOKIE)


def exigir_login(request: Request, db: Session = Depends(get_db)) -> Usuario | None:
    """Protege as rotas: exige sessão válida e, para alterar algo, um perfil que não seja só leitura."""
    if not settings.auth_ativo:
        request.state.usuario = None
        return None
    u = auth.usuario_da_sessao(db, _token(request))
    if u is None:
        raise HTTPException(401, "Faça login para continuar.")
    if request.method not in ("GET", "HEAD", "OPTIONS") and u.papel == "leitura":
        raise HTTPException(403, "Seu perfil é só de leitura.")
    request.state.usuario = u
    return u


def exigir_papel(*papeis: str, mensagem: str | None = None):
    """Dependência: exige login com um dos perfis indicados. Com o login desligado, todos são administradores."""
    nomes = ", ".join(auth.PAPEIS.get(p, p).lower() for p in papeis)

    def _dep(request: Request, db: Session = Depends(get_db)) -> Usuario | None:
        u = exigir_login(request, db)
        if settings.auth_ativo and u.papel not in papeis:
            raise HTTPException(403, mensagem or f"Ação permitida só para: {nomes}.")
        return u

    return _dep


exigir_admin = exigir_papel("admin", mensagem="Só administradores gerenciam usuários.")


def escopo_equipe(request: Request, db: Session = Depends(get_db), _u=Depends(exigir_login)) -> list[str] | None:
    """Dependência: equipes visíveis para quem está logado (None = todas). Ver services/equipes."""
    from ..services import equipes

    return equipes.escopo(db, getattr(request.state, "usuario", None))


def nome_do_usuario(request: Request) -> str | None:
    u = getattr(request.state, "usuario", None)
    return u.nome if u else None


def _set_cookie(resp: Response, token: str) -> None:
    resp.set_cookie(COOKIE, token, max_age=settings.sessao_horas * 3600, httponly=True, samesite="lax",
                    secure=settings.cookie_seguro, path="/")


class LoginIn(BaseModel):
    email: str
    senha: str


Papel = Literal["admin", "supervisor", "monitora", "leitura"]


class NovoUsuarioIn(BaseModel):
    email: str
    nome: str
    senha: str
    papel: Papel = "supervisor"

    @model_validator(mode="after")
    def _validar(self):
        if "@" not in self.email or not self.nome.strip():
            raise ValueError("Informe e-mail e nome.")
        if len(self.senha) < auth.SENHA_MINIMA:
            raise ValueError(f"A senha precisa ter ao menos {auth.SENHA_MINIMA} caracteres.")
        return self


class PrimeiroAcessoIn(BaseModel):
    email: str
    nome: str
    senha: str


# --------------------------------------------------------------------------- sessão
@router.get("/auth/estado")
def estado(request: Request, db: Session = Depends(get_db)):
    u = auth.usuario_da_sessao(db, _token(request)) if settings.auth_ativo else None
    return {"auth_ativo": settings.auth_ativo, "precisa_configurar": settings.auth_ativo and auth.total_usuarios(db) == 0,
            "usuario": auth.serializar(u) if u else None}


@router.post("/auth/primeiro-acesso")
def primeiro_acesso(dados: PrimeiroAcessoIn, response: Response, db: Session = Depends(get_db)):
    """Cria o primeiro administrador. Só funciona enquanto não existir nenhum usuário."""
    if auth.total_usuarios(db) > 0:
        raise HTTPException(409, "O sistema já foi configurado. Peça acesso a um administrador.")
    try:
        u = auth.criar_usuario(db, dados.email, dados.nome, dados.senha, "admin")
    except ValueError as e:
        raise HTTPException(422, str(e))
    u.ultimo_login_em = agora()
    db.commit()
    _set_cookie(response, auth.criar_sessao(db, u))
    return auth.serializar(u)


@router.post("/auth/login")
def login(dados: LoginIn, response: Response, db: Session = Depends(get_db)):
    u, erro = auth.autenticar(db, dados.email, dados.senha)
    if not u:
        raise HTTPException(429 if erro and "tentativas" in erro else 401, erro)
    token = auth.criar_sessao(db, u)
    _set_cookie(response, token)
    return {**auth.serializar(u), "token": token}


@router.post("/auth/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    auth.encerrar_sessao(db, _token(request))
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@router.get("/auth/eu")
def eu(u: Usuario | None = Depends(exigir_login)):
    if u is None:
        return {"id": 0, "email": "", "nome": "Acesso local", "papel": "admin", "papel_label": "Login desligado", "ativo": True}
    return auth.serializar(u)


class SenhaIn(BaseModel):
    atual: str
    nova: str


@router.post("/auth/senha")
def trocar_senha(dados: SenhaIn, request: Request, db: Session = Depends(get_db)):
    u = auth.usuario_da_sessao(db, _token(request))
    if u is None:
        raise HTTPException(401, "Faça login para continuar.")
    if not auth.verificar_senha(dados.atual, u.senha_hash):
        raise HTTPException(403, "Senha atual incorreta.")
    if len(dados.nova) < auth.SENHA_MINIMA:
        raise HTTPException(422, f"A nova senha precisa ter ao menos {auth.SENHA_MINIMA} caracteres.")
    u.senha_hash = auth.hash_senha(dados.nova)
    db.commit()
    return {"ok": True}


# --------------------------------------------------------------------------- usuários (admin)
@router.get("/usuarios", dependencies=[Depends(exigir_admin)])
def listar(db: Session = Depends(get_db)):
    return [auth.serializar(u) for u in db.scalars(select(Usuario).order_by(Usuario.nome))]


@router.post("/usuarios", dependencies=[Depends(exigir_admin)])
def criar(dados: NovoUsuarioIn, db: Session = Depends(get_db)):
    if db.scalars(select(Usuario).where(Usuario.email == auth.normalizar_email(dados.email))).first():
        raise HTTPException(409, "Já existe um usuário com este e-mail.")
    u = auth.criar_usuario(db, dados.email, dados.nome, dados.senha, dados.papel)
    db.commit()
    return auth.serializar(u)


class EditarUsuarioIn(BaseModel):
    nome: str | None = None
    papel: Papel | None = None
    ativo: bool | None = None
    senha: str | None = None


@router.patch("/usuarios/{uid}", dependencies=[Depends(exigir_admin)])
def editar(uid: int, dados: EditarUsuarioIn, db: Session = Depends(get_db)):
    u = db.get(Usuario, uid)
    if not u:
        raise HTTPException(404, "Usuário não encontrado")
    deixa_de_ser_admin = u.papel == "admin" and u.ativo and (
        (dados.papel is not None and dados.papel != "admin") or dados.ativo is False)
    if deixa_de_ser_admin and auth.admins_ativos(db) <= 1:
        raise HTTPException(409, "É preciso manter ao menos um administrador ativo.")
    if dados.nome is not None and dados.nome.strip():
        u.nome = dados.nome.strip()[:80]
    if dados.papel is not None:
        u.papel = dados.papel
    if dados.ativo is not None:
        u.ativo = dados.ativo
        if not dados.ativo:
            auth.encerrar_todas(db, u.id)
    if dados.senha:
        if len(dados.senha) < auth.SENHA_MINIMA:
            raise HTTPException(422, f"A senha precisa ter ao menos {auth.SENHA_MINIMA} caracteres.")
        u.senha_hash, u.falhas_login, u.bloqueado_ate = auth.hash_senha(dados.senha), 0, None
        auth.encerrar_todas(db, u.id)
    db.commit()
    return auth.serializar(u)
