"""Fila em processo (thread) para baixar áudio + qualificar. Troque por Celery/Redis ao escalar."""
import logging
import queue
import threading

from sqlalchemy import select

from .database import SessionLocal
from .models import Call
from .services import argus_client, pipeline

log = logging.getLogger("worker")
_q: "queue.Queue[tuple[int, bool]]" = queue.Queue()
_queued: set[int] = set()
_lock = threading.Lock()


def enqueue(call_id: int, force: bool = False) -> bool:
    with _lock:
        if call_id in _queued:
            return False
        _queued.add(call_id)
    _q.put((call_id, force))
    return True


def enqueue_pending(limit: int | None = None, include_awaiting: bool = True) -> int:
    statuses = ["pending", "error"] + (["awaiting_ai"] if include_awaiting else [])
    with SessionLocal() as db:
        stmt = select(Call.id).where(Call.status.in_(statuses)).order_by(Call.data_ligacao)
        if limit:
            stmt = stmt.limit(limit)
        return sum(enqueue(i) for i in db.scalars(stmt))


def queue_size() -> int:
    return _q.qsize()


def _run():
    while True:
        cid, force = _q.get()
        try:
            with SessionLocal() as db:
                call = db.get(Call, cid)
                if not call:
                    continue
                if not call.caminho_audio and call.origem == "argus" and call.id_campanha and call.id_ligacao:
                    try:
                        call.caminho_audio = str(argus_client.download_gravacao(call.id_campanha, call.id_ligacao))
                        db.commit()
                    except Exception as e:
                        call.status, call.erro = "error", f"download: {str(e)[:300]}"
                        db.commit()
                        continue
                pipeline.qualificar_call(db, call, force=force)
        except Exception:
            log.exception("falha ao processar call %s", cid)
        finally:
            with _lock:
                _queued.discard(cid)
            _q.task_done()


def start(n_threads: int = 2):
    for i in range(n_threads):
        threading.Thread(target=_run, name=f"worker-{i}", daemon=True).start()
