import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import worker
from .api import auth, avaliacoes, calls, monitoramento, saude, supervisao, sync, tabulacoes, webhooks
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


def _ciclo_monitoramento() -> None:
    """Avalia os alertas e, na hora certa, gera e envia o relatório do dia."""
    from .database import SessionLocal
    from .models import agora
    from .services import alertas, relatorio

    with SessionLocal() as db:
        alertas.avaliar(db)
        t = agora()
        if relatorio.deve_gerar(t, relatorio.ultimo_gerado(db)):
            relatorio.enviar(db, relatorio.gerar(db, t.date()))


async def _monitorar():
    while True:
        await asyncio.sleep(max(1, settings.alerta_intervalo_minutos) * 60)
        try:
            await asyncio.to_thread(_ciclo_monitoramento)
        except Exception:  # pragma: no cover
            log.exception("monitoramento (alertas/relatório)")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    worker.start()
    task = asyncio.create_task(_poll_argus()) if settings.argus_token and argus_client.campaign_ids() else None
    monitor = asyncio.create_task(_monitorar())
    yield
    monitor.cancel()
    if task:
        task.cancel()


app = FastAPI(title="Crivo", description="Auditoria de ligações: tabulação do Argus × monitoria humana",
              version="0.4.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_list, allow_methods=["*"], allow_headers=["*"])
protegido = [Depends(auth.exigir_login)]  # o webhook do Argus usa segredo próprio; /health fica aberto
app.include_router(auth.router)
app.include_router(calls.router, dependencies=protegido)
app.include_router(webhooks.router)
app.include_router(sync.router, dependencies=protegido)
app.include_router(saude.router, dependencies=protegido)
app.include_router(tabulacoes.router, dependencies=protegido)
app.include_router(monitoramento.router, dependencies=protegido)
app.include_router(avaliacoes.router, dependencies=protegido)
app.include_router(supervisao.router, dependencies=protegido)


@app.get("/health")
def health():
    return {"ok": True, "argus": bool(settings.argus_token)}
