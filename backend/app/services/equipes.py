"""Escopo por equipe (P2): o supervisor só vê as ligações, avaliações e feedbacks das equipes dele.

A equipe da ligação é o grupo do Argus (`calls.grupo_origem`). Admin, monitora e leitura veem tudo.
Supervisor sem equipe vinculada não vê nada (o admin vincula em Usuários).
"""
from sqlalchemy import false, select
from sqlalchemy.orm import Session

from ..models import Call, SupervisorGrupo, Usuario


def grupos_do(db: Session, usuario_id: int) -> list[str]:
    return list(db.scalars(select(SupervisorGrupo.grupo).where(SupervisorGrupo.usuario_id == usuario_id)
                           .order_by(SupervisorGrupo.grupo)))


def escopo(db: Session, usuario: Usuario | None) -> list[str] | None:
    """None = sem restrição. Lista (pode ser vazia) = só essas equipes."""
    if usuario is None or usuario.papel != "supervisor":
        return None
    return grupos_do(db, usuario.id)


def filtro(grupos: list[str]):
    """Condição SQL "ligação de uma destas equipes" (lista vazia = nenhuma)."""
    return Call.grupo_origem.in_(grupos) if grupos else false()


def no_escopo(call: Call, grupos: list[str] | None) -> bool:
    return grupos is None or (call.grupo_origem is not None and call.grupo_origem in grupos)


def definir(db: Session, usuario_id: int, grupos: list[str]) -> list[str]:
    limpos = sorted({g.strip() for g in grupos if g and g.strip()})
    db.query(SupervisorGrupo).filter(SupervisorGrupo.usuario_id == usuario_id).delete()
    db.add_all(SupervisorGrupo(usuario_id=usuario_id, grupo=g) for g in limpos)
    db.flush()
    return limpos
