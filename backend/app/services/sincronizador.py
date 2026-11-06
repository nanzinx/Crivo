"""Sincronização com o Argus: polling de fallback e backfill. Toda execução registra sucesso/falha
no painel de saúde (antes, erros eram engolidos e a perda de ligações passava despercebida)."""
import logging
from datetime import date, datetime, time, timedelta

from ..database import SessionLocal
from . import argus_client, status

log = logging.getLogger("sincronizador")


def _janelas(data_inicio: date | None, data_fim: date | None) -> list[tuple[datetime, datetime]]:
    ini = datetime.combine(data_inicio or date.today(), time.min)
    fim = datetime.combine(data_fim or date.today(), time.max)
    out, cur = [], ini
    while cur < fim:  # API aceita no máximo 7 dias por consulta
        out.append((cur, min(cur + timedelta(days=7) - timedelta(seconds=1), fim)))
        cur += timedelta(days=7)
    return out


def sincronizar(ultimos_minutos: int | None = None, data_inicio: date | None = None,
                data_fim: date | None = None, chave: str = status.SYNC_MANUAL) -> dict:
    """Busca /report/ligacoesdetalhadas de todas as campanhas, faz upsert e enfileira para qualificação."""
    from .. import worker
    from ..api.webhooks import upsert_from_argus

    ids = argus_client.campaign_ids()
    if not ids:
        msg = "Defina ARGUS_CAMPAIGN_IDS"
        status.registrar(chave, False, msg)
        return {"ok": False, "erro": msg, "ligacoes": 0, "enfileiradas": 0}

    janelas = [(None, None)] if ultimos_minutos else _janelas(data_inicio, data_fim)
    novos = enfileirados = 0
    try:
        with SessionLocal() as db:
            for camp in ids:
                for a, b in janelas:
                    for item in argus_client.ligacoes_detalhadas(camp, a, b, ultimos_minutos):
                        item.setdefault("idCampanha", camp)
                        call = upsert_from_argus(db, item)
                        if call:
                            novos += 1
                            enfileirados += worker.enqueue(call.id)
    except Exception as e:
        log.exception("falha ao sincronizar com o Argus")
        status.registrar(chave, False, f"{type(e).__name__}: {e}")
        return {"ok": False, "erro": str(e), "ligacoes": novos, "enfileiradas": enfileirados}

    status.registrar(chave, True, f"{novos} ligações recebidas, {enfileirados} enfileiradas")
    return {"ok": True, "ligacoes": novos, "enfileiradas": enfileirados}


def sincronizar_recentes(ultimos_minutos: int = 15) -> dict:
    """Usado pelo polling automático."""
    return sincronizar(ultimos_minutos=ultimos_minutos, chave=status.POLLING)
