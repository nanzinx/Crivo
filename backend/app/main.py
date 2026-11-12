import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import worker
from .api import calls, saude, sync, webhooks
from .config import settings
from .database import init_db
from .services import argus_client, sincronizador

log = logging.getLogger("crivo")


async def _poll_argus():
    """Fallback: periodicamente busca as ligações recentes (cobre falhas de webhook).

    Roda em thread para não bloquear a API (o cliente Argus é síncrono, timeout de 120 s).
    Sucesso e falha ficam registrados em /api/v1/saude.
    """
    intervalo = max(1, settings.argus_poll_minutos) * 60
    while True:
        await asyncio.sleep(intervalo)
        try:
            await asyncio.to_thread(sincronizador.sincronizar_recentes, settings.argus_poll_minutos * 3)
        except Exception:  # pragma: no cover - sincronizar já registra a falha
            log.exception("polling Argus")


async def _retomar_aguardando():
    """A cada 10 min, retoma as ligações "aguardando IA" quando há chave e o teto diário permite."""
    from .database import SessionLocal
    from .services import custos

    while True:
        await asyncio.sleep(600)
        try:
            if not settings.openai_api_key:
                continue
            with SessionLocal() as db:
                bloqueado = custos.teto_atingido(db)
            if not bloqueado:
                await asyncio.to_thread(worker.enqueue_aguardando)
        except Exception:  # pragma: no cover
            log.exception("retomada de ligações aguardando IA")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    worker.start()
    task = asyncio.create_task(_poll_argus()) if settings.argus_token and argus_client.campaign_ids() else None
    retomada = asyncio.create_task(_retomar_aguardando())
    yield
    retomada.cancel()
    if task:
        task.cancel()


app = FastAPI(title="Crivo", description="Auditoria de ligações: Argus × IA", version="0.3.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_list, allow_methods=["*"], allow_headers=["*"])
app.include_router(calls.router)
app.include_router(webhooks.router)
app.include_router(sync.router)
app.include_router(saude.router)


@app.get("/health")
def health():
    return {"ok": True, "ia": "openai" if settings.openai_api_key else "sem-chave",
            "argus": bool(settings.argus_token)}
