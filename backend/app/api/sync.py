from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import worker
from ..database import get_db
from ..services import argus_client, local_ingestor, pipeline
from .webhooks import upsert_from_argus

router = APIRouter(prefix="/api/v1/sync", tags=["sync"])


@router.post("/local")
def sync_local(limit: int | None = None, db: Session = Depends(get_db)):
    """Importa a pasta Gravações + CSV legado + HTML enriquecido."""
    folder = local_ingestor.import_folder(db, limit=limit)
    csv_ = local_ingestor.import_legacy_csv(db)
    html_ = local_ingestor.import_legacy_html(db)
    return {"pasta": folder, "csv": csv_, "html": html_, "identidades_revalidadas": pipeline.revalidar_identidades(db)}


@router.post("/argus")
def sync_argus(data_inicio: date | None = None, data_fim: date | None = None, ultimos_minutos: int | None = None,
               db: Session = Depends(get_db)):
    """Polling/backfill via /report/ligacoesdetalhadas (intervalo máx. 7 dias por consulta)."""
    ids = argus_client.campaign_ids()
    if not ids:
        raise HTTPException(400, "Defina ARGUS_CAMPAIGN_IDS")
    novos = enfileirados = 0
    try:
        for camp in ids:
            if ultimos_minutos:
                windows = [(None, None)]
            else:
                ini = datetime.combine(data_inicio or date.today(), time.min)
                fim = datetime.combine(data_fim or date.today(), time.max)
                windows, cur = [], ini
                while cur < fim:
                    windows.append((cur, min(cur + timedelta(days=7) - timedelta(seconds=1), fim)))
                    cur += timedelta(days=7)
            for a, b in windows:
                for item in argus_client.ligacoes_detalhadas(camp, a, b, ultimos_minutos):
                    item.setdefault("idCampanha", camp)
                    call = upsert_from_argus(db, item)
                    if call:
                        novos += 1
                        enfileirados += worker.enqueue(call.id)
    except Exception as e:
        raise HTTPException(502, f"Falha Argus: {e}")
    return {"ligacoes": novos, "enfileiradas": enfileirados}


@router.post("/process")
def process_pending(limit: int | None = None, include_awaiting: bool = True):
    return {"enfileiradas": worker.enqueue_pending(limit, include_awaiting)}


@router.post("/reprocess/{call_id}")
def reprocess(call_id: int):
    return {"enfileirada": worker.enqueue(call_id, force=True)}


@router.get("/status")
def status():
    return {"fila": worker.queue_size()}
