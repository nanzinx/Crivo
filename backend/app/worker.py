"""Fila em processo (thread) para baixar a gravação e pôr a ligação na fila da monitora.

Troque por Celery/Redis ao escalar.
"""
import logging
import queue
import threading

from .database import SessionLocal
from .models import Call
from .services import pipeline

log = logging.getLogger("worker")
_q: "queue.Queue[tuple[int, bool]]" = queue.Queue()
_queued: set[int] = set()
_lock = threading.Lock()


def enqueue(call_id: int, force: bool = False) -> bool:
    """`force`: baixa a gravação de novo mesmo que ela já exista."""
    with _lock:
        if call_id in _queued:
            return False
        _queued.add(call_id)
    _q.put((call_id, force))
    return True


def queue_size() -> int:
    return _q.qsize()


def _run():
    while True:
        cid, force = _q.get()
        try:
            with SessionLocal() as db:
                call = db.get(Call, cid)
                if call:
                    pipeline.preparar_call(db, call, baixar_de_novo=force)
        except Exception:
            log.exception("falha ao processar call %s", cid)
        finally:
            with _lock:
                _queued.discard(cid)
            _q.task_done()


def start(n_threads: int = 2):
    for i in range(n_threads):
        threading.Thread(target=_run, name=f"worker-{i}", daemon=True).start()
