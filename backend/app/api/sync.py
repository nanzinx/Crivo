from datetime import date

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import worker
from ..database import get_db
from ..models import Call
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
    """Polling/backfill via /report/ligacoesdetalhadas (janelas de até 7 dias por consulta).

    As ligações novas entram na fila de download da gravação e depois na fila de avaliação."""
    res = sincronizador.sincronizar(ultimos_minutos, data_inicio, data_fim)
    if not res["ok"]:
        code = 400 if "ARGUS_CAMPAIGN_IDS" in res.get("erro", "") else 502
        raise HTTPException(code, f"Falha Argus: {res['erro']}")
    return res


@router.post("/process")
def baixar_pendentes(limit: int | None = 500, db: Session = Depends(get_db)):
    """Põe na fila de download as ligações sem gravação ainda (pendentes ou com erro no download)."""
    from ..services import avaliacoes

    ids = db.scalars(select(Call.id).where(Call.status.in_((avaliacoes.PENDENTE, avaliacoes.ERRO)))
                     .order_by(Call.id.desc()).limit(limit)).all()
    return {"enfileiradas": sum(worker.enqueue(i) for i in ids)}


@router.post("/reprocess/{call_id}")
def reprocess(call_id: int, db: Session = Depends(get_db)):
    """Baixa a gravação da ligação de novo (ex.: arquivo corrompido ou falha no download). Não desfaz a avaliação."""
    if not db.get(Call, call_id):
        raise HTTPException(404, "Ligação não encontrada")
    return {"enfileirada": worker.enqueue(call_id, force=True)}


@router.get("/status")
def fila_status():
    return {"fila": worker.queue_size()}
