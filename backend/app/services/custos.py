"""Medição do gasto com IA: cada chamada paga vira uma linha em ia_uso.

Os valores são ESTIMATIVAS pelo preço de tabela (US$). Preços mudam: confira a página de preços do
provedor e, se precisar, sobrescreva no .env (PRECO_TRANSCRICAO_MINUTO, PRECO_ENTRADA_1M, PRECO_SAIDA_1M).
"""
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Call, IaUso, agora

# US$ por minuto de áudio
PRECOS_TRANSCRICAO = {
    "whisper-1": 0.006,
    "gpt-4o-transcribe": 0.006,
    "gpt-4o-mini-transcribe": 0.003,
    "gpt-transcribe": 0.0045,
}
# US$ por 1 milhão de tokens (entrada, saída)
PRECOS_CHAT = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1-nano": (0.10, 0.40),
}


def preco_transcricao(modelo: str) -> float | None:
    if settings.preco_transcricao_minuto > 0:
        return settings.preco_transcricao_minuto
    return PRECOS_TRANSCRICAO.get(modelo)


def preco_chat(modelo: str) -> tuple[float, float] | None:
    if settings.preco_entrada_1m > 0 or settings.preco_saida_1m > 0:
        return settings.preco_entrada_1m, settings.preco_saida_1m
    return PRECOS_CHAT.get(modelo)


def calcular(tipo: str, modelo: str, audio_segundos: float = 0, tokens_entrada: int = 0, tokens_saida: int = 0) -> float:
    if tipo == "transcricao":
        return (audio_segundos / 60) * (preco_transcricao(modelo) or 0)
    ent, sai = preco_chat(modelo) or (0, 0)
    return tokens_entrada * ent / 1e6 + tokens_saida * sai / 1e6


def registrar(db: Session, call: Call | None, tipo: str, modelo: str, audio_segundos: float = 0,
              tokens_entrada: int = 0, tokens_saida: int = 0) -> float:
    """Registra uma chamada paga e soma no acumulado da ligação. Não faz commit."""
    custo = calcular(tipo, modelo, audio_segundos, tokens_entrada, tokens_saida)
    db.add(IaUso(call_id=call.id if call else None, tipo=tipo, modelo=modelo, audio_segundos=audio_segundos or 0,
                 tokens_entrada=tokens_entrada or 0, tokens_saida=tokens_saida or 0, custo_usd=custo, em=agora()))
    if call is not None:
        call.custo_usd = (call.custo_usd or 0) + custo
    return custo


def _inicio_do_dia(d: datetime | None = None) -> datetime:
    return (d or agora()).replace(hour=0, minute=0, second=0, microsecond=0)


def gasto_desde(db: Session, desde: datetime) -> float:
    return db.scalar(select(func.coalesce(func.sum(IaUso.custo_usd), 0.0)).where(IaUso.em >= desde)) or 0.0


def gasto_hoje(db: Session) -> float:
    return gasto_desde(db, _inicio_do_dia())


def teto_atingido(db: Session) -> bool:
    teto = settings.ia_teto_diario_usd
    return teto > 0 and gasto_hoje(db) >= teto


def modelos_sem_preco() -> list[str]:
    out = []
    if settings.openai_api_key:
        if preco_transcricao(settings.openai_whisper_model) is None:
            out.append(settings.openai_whisper_model)
        if preco_chat(settings.openai_model) is None:
            out.append(settings.openai_model)
    return out


def resumo(db: Session, dias: int = 14) -> dict:
    hoje = _inicio_do_dia()
    mes = hoje.replace(day=1)
    gasto_h, gasto_m = gasto_desde(db, hoje), gasto_desde(db, mes)
    ligacoes_ia = db.scalar(select(func.count(func.distinct(IaUso.call_id))).where(IaUso.em >= mes)) or 0
    minutos = (db.scalar(select(func.coalesce(func.sum(IaUso.audio_segundos), 0.0)).where(IaUso.em >= mes)) or 0) / 60
    sem_ia = db.scalar(select(func.count(Call.id)).where(Call.motor == "local", Call.qualificado_em >= mes)) or 0

    dia = func.date(IaUso.em)
    por_dia = dict(db.execute(select(dia, func.sum(IaUso.custo_usd)).where(IaUso.em >= hoje - timedelta(days=dias - 1))
                              .group_by(dia)).all())
    serie = []
    for i in range(dias - 1, -1, -1):
        d = (hoje - timedelta(days=i)).date().isoformat()
        serie.append({"data": d, "usd": round(float(por_dia.get(d, 0) or 0), 4)})

    teto = settings.ia_teto_diario_usd
    return {
        "hoje_usd": round(gasto_h, 4),
        "mes_usd": round(gasto_m, 4),
        "ligacoes_com_ia_mes": ligacoes_ia,
        "custo_medio_usd": round(gasto_m / ligacoes_ia, 5) if ligacoes_ia else 0,
        "minutos_transcritos_mes": round(minutos, 1),
        "resolvidas_sem_ia_mes": sem_ia,
        "teto_diario_usd": teto,
        "teto_pct": round(100 * gasto_h / teto, 1) if teto > 0 else None,
        "modelo_transcricao": settings.openai_whisper_model,
        "modelo_classificacao": settings.openai_model,
        "diarizacao": settings.ia_diarizar,
        "modelos_sem_preco": modelos_sem_preco(),
        "serie": serie,
    }
