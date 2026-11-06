import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import worker
from .api import calls, sync, webhooks
from .config import settings
from .database import init_db
from .services import argus_client


async def _poll_argus():
    """Fallback: a cada 5 min busca ligações dos últimos 15 min (cobre falhas de webhook)."""
    from .database import SessionLocal

    while True:
        await asyncio.sleep(300)
        try:
            for camp in argus_client.campaign_ids():
                with SessionLocal() as db:
                    for item in argus_client.ligacoes_detalhadas(camp, ultimos_minutos=15):
                        item.setdefault("idCampanha", camp)
                        c = webhooks.upsert_from_argus(db, item)
                        if c:
                            worker.enqueue(c.id)
        except Exception:
            pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    worker.start()
    task = asyncio.create_task(_poll_argus()) if settings.argus_token and argus_client.campaign_ids() else None
    yield
    if task:
        task.cancel()


app = FastAPI(title="Supervisor Argus", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(calls.router)
app.include_router(webhooks.router)
app.include_router(sync.router)


@app.get("/health")
def health():
    return {"ok": True, "ia": "openai" if settings.openai_api_key else "sem-chave",
            "argus": bool(settings.argus_token)}
