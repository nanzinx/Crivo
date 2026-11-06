"""Registro do último resultado de cada integração (alimenta o painel de saúde)."""
import logging

from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..models import SystemStatus, agora

log = logging.getLogger("status")

# chaves conhecidas
WEBHOOK = "argus_webhook"
POLLING = "argus_polling"
SYNC_MANUAL = "argus_sync"
DOWNLOAD = "argus_download"
IA = "ia"
IMPORTACAO = "importacao_local"
CRUZAMENTO = "cruzamento"


def registrar(chave: str, ok: bool, detalhe: str | None = None, db: Session | None = None) -> None:
    """Grava o resultado sem nunca derrubar o fluxo que o chamou."""
    own = db is None
    s = db or SessionLocal()
    try:
        row = s.get(SystemStatus, chave) or SystemStatus(chave=chave)
        now = agora()
        row.ok, row.em, row.detalhe = ok, now, (detalhe or None) and str(detalhe)[:1000]
        if ok:
            row.ultimo_sucesso_em = now
        else:
            row.ultima_falha_em = now
        s.add(row)
        s.commit()
    except Exception:  # pragma: no cover - status é best-effort
        log.exception("falha ao registrar status %s", chave)
        if own:
            s.rollback()
    finally:
        if own:
            s.close()


def todos(db: Session) -> dict[str, dict]:
    iso = lambda d: d.isoformat() if d else None  # noqa: E731
    return {
        r.chave: {
            "ok": r.ok,
            "em": iso(r.em),
            "detalhe": r.detalhe,
            "ultimo_sucesso_em": iso(r.ultimo_sucesso_em),
            "ultima_falha_em": iso(r.ultima_falha_em),
        }
        for r in db.query(SystemStatus).all()
    }
