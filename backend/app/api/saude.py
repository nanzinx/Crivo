"""Painel de saúde: integrações, fila, erros e alertas acionáveis."""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import worker
from ..config import settings
from ..database import get_db
from ..models import Call, agora
from ..services import argus_client, status

router = APIRouter(prefix="/api/v1", tags=["saude"])

NOMES = {
    status.WEBHOOK: "Webhook Argus",
    status.POLLING: "Polling Argus",
    status.SYNC_MANUAL: "Sincronização manual",
    status.DOWNLOAD: "Download de gravações",
    status.IA: "Qualificação por IA",
    status.IMPORTACAO: "Importação local",
    status.CRUZAMENTO: "Cruzamento com a discadora",
}


def _em_horario_comercial(now: datetime) -> bool:
    try:
        ini, fim = (int(x) for x in settings.horario_comercial.split("-"))
    except ValueError:
        ini, fim = 8, 20
    return now.weekday() < 6 and ini <= now.hour < fim


def _alertas(eventos: dict, por_status: dict, fila: int, now: datetime) -> list[dict]:
    out: list[dict] = []
    add = lambda nivel, titulo, msg: out.append({"nivel": nivel, "titulo": titulo, "mensagem": msg})  # noqa: E731
    argus_on = bool(settings.argus_token)

    for chave in (status.POLLING, status.SYNC_MANUAL, status.DOWNLOAD, status.IA, status.CRUZAMENTO):
        ev = eventos.get(chave)
        if ev and not ev["ok"]:
            add("critico", f"{NOMES[chave]} falhando", ev["detalhe"] or "Última execução falhou.")

    if argus_on:
        wh = eventos.get(status.WEBHOOK)
        if not wh:
            add("atencao", "Nenhum webhook recebido",
                "Configure no Argus o webhook de Tabulação apontando para /api/v1/webhooks/argus.")
        elif _em_horario_comercial(now):
            ultimo = datetime.fromisoformat(wh["em"])
            if now - ultimo > timedelta(minutes=settings.alerta_webhook_minutos):
                mins = int((now - ultimo).total_seconds() // 60)
                add("atencao", "Webhook silencioso", f"Nenhum webhook há {mins} min em horário de operação.")
        if not argus_client.campaign_ids():
            add("atencao", "Polling desligado", "Defina ARGUS_CAMPAIGN_IDS para ativar o polling de segurança.")

    aguardando = por_status.get("awaiting_ai", 0)
    if aguardando and not settings.openai_api_key:
        add("atencao", "IA não configurada", f"{aguardando} ligações aguardando OPENAI_API_KEY.")
    if erros := por_status.get("error", 0):
        add("atencao", "Ligações com erro", f"{erros} ligações falharam e podem ser reprocessadas.")
    if fila > settings.alerta_fila_max:
        add("atencao", "Fila acumulada", f"{fila} ligações aguardando processamento.")
    return out


@router.get("/saude")
def saude(db: Session = Depends(get_db)):
    now = agora()
    eventos = status.todos(db)
    for k, v in eventos.items():
        v["nome"] = NOMES.get(k, k)
    por_status = dict(db.execute(select(Call.status, func.count()).group_by(Call.status)).all())
    fila = worker.queue_size()

    erros = db.scalars(select(Call).where(Call.status == "error").order_by(Call.id.desc()).limit(15)).all()
    ultimas_24h = db.scalar(select(func.count(Call.id)).where(Call.criado_em >= now - timedelta(hours=24))) or 0
    ultima = db.scalar(select(func.max(Call.data_ligacao)))

    return {
        "gerado_em": now.isoformat(),
        "integracoes": {
            "ia": {"configurada": bool(settings.openai_api_key), "modelo": settings.openai_model,
                   "transcricao": settings.openai_whisper_model},
            "argus": {"configurado": bool(settings.argus_token), "campanhas": argus_client.campaign_ids(),
                      "polling_minutos": settings.argus_poll_minutos},
        },
        "fila": {"tamanho": fila},
        "status_ligacoes": {k: por_status.get(k, 0) for k in ("pending", "awaiting_ai", "done", "error")},
        "recebidas_24h": ultimas_24h,
        "ultima_ligacao_em": ultima.isoformat() if ultima else None,
        "eventos": eventos,
        "erros_recentes": [
            {"id": c.id, "id_ligacao": c.id_ligacao, "data_ligacao": c.data_ligacao.isoformat() if c.data_ligacao else None,
             "erro": c.erro, "operador_nome": c.operador_nome}
            for c in erros
        ],
        "alertas": _alertas(eventos, por_status, fila, now),
    }
