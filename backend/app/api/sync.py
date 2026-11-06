from datetime import date

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from .. import worker
from ..database import get_db
from ..services import local_ingestor, pipeline, sincronizador, status

router = APIRouter(prefix="/api/v1/sync", tags=["sync"])


@router.post("/local")
def sync_local(limit: int | None = None, db: Session = Depends(get_db)):
    """Importa a pasta de gravações + CSV de escuta + HTML legado e CRUZA com o relatório da discadora."""
    try:
        folder = local_ingestor.import_folder(db, limit=limit)
        csv_ = local_ingestor.import_legacy_csv(db)
        html_ = local_ingestor.import_legacy_html(db)
        cruz = local_ingestor.import_cruzar_dados(db)
        ident = pipeline.revalidar_identidades(db)
    except Exception as e:
        db.rollback()
        status.registrar(status.IMPORTACAO, False, f"{type(e).__name__}: {e}")
        raise HTTPException(500, f"Falha na importação: {e}")
    status.registrar(status.IMPORTACAO, True,
                     f"{folder.get('novas', 0)} novas, {folder.get('vinculadas', 0)} vinculadas")
    status.registrar(status.CRUZAMENTO, "erro" not in cruz,
                     cruz.get("erro") or f"{cruz['linhas_enriquecidas']} linhas cruzadas")
    return {"pasta": folder, "csv": csv_, "html": html_, "cruzamento": cruz, "identidades_revalidadas": ident}


@router.post("/cruzar")
async def sync_cruzar(arquivo: UploadFile | None = File(None), db: Session = Depends(get_db)):
    """Cruza o relatório detalhado da discadora. Envie o CSV (upload) ou use o caminho CRUZAR_CSV do .env."""
    conteudo = await arquivo.read() if arquivo else None
    res = local_ingestor.import_cruzar_dados(db, conteudo=conteudo)
    status.registrar(status.CRUZAMENTO, "erro" not in res,
                     res.get("erro") or f"{res['linhas_enriquecidas']} linhas cruzadas")
    if "erro" in res and arquivo:
        raise HTTPException(400, res["erro"])
    return res


@router.post("/argus")
def sync_argus(data_inicio: date | None = None, data_fim: date | None = None, ultimos_minutos: int | None = None):
    """Polling/backfill via /report/ligacoesdetalhadas (janelas de até 7 dias por consulta)."""
    res = sincronizador.sincronizar(ultimos_minutos, data_inicio, data_fim)
    if not res["ok"]:
        code = 400 if "ARGUS_CAMPAIGN_IDS" in res.get("erro", "") else 502
        raise HTTPException(code, f"Falha Argus: {res['erro']}")
    return res


@router.post("/process")
def process_pending(limit: int | None = None, include_awaiting: bool = True):
    return {"enfileiradas": worker.enqueue_pending(limit, include_awaiting)}


@router.post("/reprocess/{call_id}")
def reprocess(call_id: int):
    return {"enfileirada": worker.enqueue(call_id, force=True)}


@router.get("/status")
def fila_status():
    return {"fila": worker.queue_size()}
