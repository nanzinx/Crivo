"""Qualidade da IA: acurácia contra a revisão humana e medição com o gabarito da escuta manual."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import worker
from ..config import settings
from ..database import get_db
from ..services import qualidade

router = APIRouter(prefix="/api/v1/qualidade", tags=["qualidade"])


@router.get("")
def resumo(db: Session = Depends(get_db)):
    return qualidade.medir(db)


@router.post("/medir")
def medir_com_gabarito(n: int = Query(50, ge=1, le=2000), db: Session = Depends(get_db)):
    """Roda a IA em até N ligações já revisadas por humano (ex.: escuta manual) que ainda não têm resposta
    da IA. A revisão humana é mantida; a resposta da IA fica guardada para a comparação. USA A IA (custa)."""
    if not settings.openai_api_key:
        raise HTTPException(400, "Configure OPENAI_API_KEY: a medição precisa da IA de verdade.")
    calls = qualidade.candidatos_gabarito(db, n)
    enfileiradas = sum(bool(worker.enqueue(c.id, force=True)) for c in calls)
    return {"enfileiradas": enfileiradas, "custo_estimado_usd": qualidade.custo_estimado(calls)}
