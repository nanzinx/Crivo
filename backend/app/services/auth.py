"""Login: senhas com scrypt (biblioteca padrão), sessões opacas revogáveis e perfis de acesso.

Perfis:
- admin: tudo, inclusive gerenciar usuários e registrar o resultado das ligações;
- supervisor: consulta e ações (confirmar tabulações, importar, sincronizar, alertas);
- monitora: monitoria de qualidade: ouve as ligações e registra o resultado (além do que o supervisor faz);
- leitura: só consulta.
"""
import base64
import hashlib
import hmac
import secrets
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Sessao, Usuario, agora

PAPEIS = {"admin": "Administrador", "supervisor": "Supervisor", "monitora": "Monitora de qualidade",
          "leitura": "Só leitura"}
SENHA_MINIMA = 8
MAX_FALHAS = 5
BLOQUEIO_MINUTOS = 5
_N, _R, _P = 2**14, 8, 1


def hash_senha(senha: str) -> str:
    sal = secrets.token_bytes(16)
    h = hashlib.scrypt(senha.encode(), salt=sal, n=_N, r=_R, p=_P, dklen=32)
    b = lambda x: base64.b64encode(x).decode()  # noqa: E731
    return f"scrypt${_N}${_R}${_P}${b(sal)}${b(h)}"


def verificar_senha(senha: str, guardado: str) -> bool:
    try:
        _, n, r, p, sal, h = guardado.split("$")
        calc = hashlib.scrypt(senha.encode(), salt=base64.b64decode(sal), n=int(n), r=int(r), p=int(p), dklen=32)
        return hmac.compare_digest(calc, base64.b64decode(h))
    except (ValueError, TypeError):
        return False


def normalizar_email(email: str) -> str:
    return (email or "").strip().lower()


def criar_usuario(db: Session, email: str, nome: str, senha: str, papel: str) -> Usuario:
    if papel not in PAPEIS:
        raise ValueError("Perfil inválido.")
    if len(senha or "") < SENHA_MINIMA:
        raise ValueError(f"A senha precisa ter ao menos {SENHA_MINIMA} caracteres.")
    u = Usuario(email=normalizar_email(email), nome=nome.strip()[:80], senha_hash=hash_senha(senha), papel=papel)
    db.add(u)
    db.flush()
    return u


def total_usuarios(db: Session) -> int:
    return db.scalar(select(func.count(Usuario.id))) or 0


def admins_ativos(db: Session) -> int:
    return db.scalar(select(func.count(Usuario.id)).where(Usuario.papel == "admin", Usuario.ativo.is_(True))) or 0


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def autenticar(db: Session, email: str, senha: str) -> tuple[Usuario | None, str | None]:
    """Devolve (usuário, erro). Bloqueia por alguns minutos depois de várias senhas erradas."""
    u = db.scalars(select(Usuario).where(Usuario.email == normalizar_email(email))).first()
    t = agora()
    if u and u.bloqueado_ate and u.bloqueado_ate > t:
        mins = max(1, int((u.bloqueado_ate - t).total_seconds() // 60) + 1)
        return None, f"Muitas tentativas. Tente de novo em {mins} minutos."
    if not u or not u.ativo or not verificar_senha(senha or "", u.senha_hash):
        if u:
            u.falhas_login = (u.falhas_login or 0) + 1
            if u.falhas_login >= MAX_FALHAS:
                u.bloqueado_ate, u.falhas_login = t + timedelta(minutes=BLOQUEIO_MINUTOS), 0
            db.commit()
        return None, "E-mail ou senha incorretos."
    u.falhas_login, u.bloqueado_ate, u.ultimo_login_em = 0, None, t
    return u, None


def criar_sessao(db: Session, u: Usuario) -> str:
    token = secrets.token_urlsafe(32)
    db.add(Sessao(token_hash=_hash_token(token), usuario_id=u.id, expira_em=agora() + timedelta(hours=settings.sessao_horas)))
    db.commit()
    return token


def usuario_da_sessao(db: Session, token: str | None) -> Usuario | None:
    if not token:
        return None
    s = db.scalars(select(Sessao).where(Sessao.token_hash == _hash_token(token))).first()
    if not s or s.expira_em < agora():
        return None
    u = db.get(Usuario, s.usuario_id)
    return u if u and u.ativo else None


def encerrar_sessao(db: Session, token: str | None) -> None:
    if token:
        db.query(Sessao).filter(Sessao.token_hash == _hash_token(token)).delete()
        db.commit()


def encerrar_todas(db: Session, usuario_id: int) -> None:
    db.query(Sessao).filter(Sessao.usuario_id == usuario_id).delete()


def serializar(u: Usuario) -> dict:
    return {"id": u.id, "email": u.email, "nome": u.nome, "papel": u.papel, "papel_label": PAPEIS.get(u.papel, u.papel),
            "ativo": bool(u.ativo), "criado_em": u.criado_em.isoformat() if u.criado_em else None,
            "ultimo_login_em": u.ultimo_login_em.isoformat() if u.ultimo_login_em else None}
