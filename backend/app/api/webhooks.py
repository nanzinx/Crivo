from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import worker
from ..config import settings
from ..database import get_db
from ..models import Call
from ..services import status

router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])


def _dt(v) -> datetime | None:
    if not v:
        return None
    s = str(v).replace("T", " ")[:19]
    for fmt in ("%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def upsert_from_argus(db: Session, p: dict, origem: str = "argus") -> Call | None:
    """Aceita payload de webhook (tipos 1/2) ou item de /report/ligacoesdetalhadas / listargravacoes."""
    g = lambda *ks: next((p[k] for k in ks if p.get(k) not in (None, "")), None)  # noqa: E731
    id_lig = g("idLigacao")
    if not id_lig:
        return None
    id_lig = int(id_lig)
    call = db.scalars(select(Call).where(Call.id_ligacao == id_lig)).first()
    if call is None:
        call = Call(id_ligacao=id_lig, origem=origem, status="pending")
        db.add(call)
    call.id_campanha = g("idCampanha") or call.id_campanha
    call.nr_lead = g("nrLead") or call.nr_lead
    call.telefone = g("telefone", "dddTelefone") or call.telefone
    call.nome_esperado = g("nomeCliente") or call.nome_esperado
    call.operador_id = g("codUsuarioIntegracao", "idUsuario") or call.operador_id
    call.operador_nome = g("nomeUsuario", "usuarioOperador") or call.operador_nome
    call.tabulacao_operador = g("tabulacaoDesc", "tabulado") or call.tabulacao_operador
    call.data_ligacao = _dt(g("dataInicioLigacao", "dataHoraLigacao")) or call.data_ligacao
    dur = g("tempoLigacao", "tempoSegundos")
    if dur is not None:
        call.duracao_segundos = float(dur)
    db.commit()
    return call


@router.post("/argus")
async def argus_webhook(request: Request, db: Session = Depends(get_db),
                        x_webhook_secret: str | None = Header(None), secret: str | None = None):
    if settings.argus_webhook_secret and (x_webhook_secret or secret) != settings.argus_webhook_secret:
        raise HTTPException(403, "Segredo inválido")
    p = await request.json()
    status.registrar(status.WEBHOOK, True, f"idTipoWebhook={p.get('idTipoWebhook')} idLigacao={p.get('idLigacao')}")
    tipo = int(p.get("idTipoWebhook", 0) or 0)
    if tipo not in (1, 2):
        return {"ok": True, "ignorado": f"idTipoWebhook={tipo}"}
    call = upsert_from_argus(db, p)
    if call is None:
        return {"ok": True, "ignorado": "sem idLigacao (tabulação sem ligação)"}
    queued = False
    if tipo == 2:  # tabulação = ligação encerrada, gravação disponível
        queued = worker.enqueue(call.id)
    return {"ok": True, "id": call.id, "enfileirado": queued}
