"""Alertas automáticos, relatório diário e teste das notificações."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import Alerta, Relatorio, agora
from ..services import alertas, notificacoes, relatorio
from .auth import nome_do_usuario

router = APIRouter(prefix="/api/v1", tags=["monitoramento"])


def _regras() -> list[dict]:
    s = settings
    return [
        {"tipo": "operador", "nome": alertas.REGRAS["operador"],
         "descricao": f"{s.alerta_operador_taxa:g}% ou mais de divergência (entre as ligações avaliadas) em {s.alerta_operador_horas}h (mínimo de "
                      f"{s.alerta_operador_min_ligacoes} ligações). Crítico com {s.alerta_operador_altas}+ divergências altas."},
        {"tipo": "tronco", "nome": alertas.REGRAS["tronco"],
         "descricao": f"{s.alerta_tronco_mudas_pct:g}% ou mais de ligações mudas em {s.alerta_tronco_horas}h (mínimo de "
                      f"{s.alerta_tronco_min_ligacoes}) e 1,5× acima dos outros troncos. Crítico a partir de 70%."},
        {"tipo": "nao_ligar", "nome": alertas.REGRAS["nao_ligar"],
         "descricao": "Cliente pediu para não ligar e a tabulação não registrou, nas últimas 24h."},
        {"tipo": "sistema", "nome": alertas.REGRAS["sistema"],
         "descricao": "Alertas críticos da Saúde do sistema (integração falhando...)."},
    ]


@router.get("/alertas")
def listar(db: Session = Depends(get_db)):
    abertos = db.scalars(select(Alerta).where(Alerta.resolvido_em.is_(None))
                         .order_by(Alerta.nivel, Alerta.aberto_em.desc())).all()
    recentes = db.scalars(select(Alerta).where(Alerta.resolvido_em.is_not(None))
                          .order_by(Alerta.resolvido_em.desc()).limit(30)).all()
    return {
        "abertos": [alertas.serializar(a) for a in abertos],
        "recentes": [alertas.serializar(a) for a in recentes],
        "canais": notificacoes.canais(),
        "regras": _regras(),
        "intervalo_minutos": settings.alerta_intervalo_minutos,
        "relatorio": {"hora": settings.relatorio_hora, "dias": settings.relatorio_dias},
    }


@router.post("/alertas/avaliar")
def avaliar(db: Session = Depends(get_db)):
    return alertas.avaliar(db)


class ReconhecerIn(BaseModel):
    por: str | None = None  # com login ligado, vale o nome do usuário da sessão


@router.post("/alertas/{alerta_id}/reconhecer")
def reconhecer(alerta_id: int, r: ReconhecerIn, request: Request, db: Session = Depends(get_db)):
    """Marca que alguém já está cuidando do alerta (ele continua aberto até a condição sumir)."""
    a = db.get(Alerta, alerta_id)
    if not a:
        raise HTTPException(404, "Alerta não encontrado")
    por = nome_do_usuario(request) or (r.por or "").strip()
    if not por:
        raise HTTPException(422, "Informe quem está cuidando do alerta.")
    a.reconhecido_por, a.reconhecido_em = por[:80], agora()
    db.commit()
    return alertas.serializar(a)


def _rel(r: Relatorio, envio: dict | None = None) -> dict:
    out = {"id": r.id, "data": r.data.isoformat(), "gerado_em": r.gerado_em.isoformat(),
           "enviado_em": r.enviado_em.isoformat() if r.enviado_em else None, "envio_detalhe": r.envio_detalhe,
           "dados": r.dados, "texto": r.texto}
    if envio is not None:
        out["envio"] = envio
    return out


@router.get("/relatorios")
def relatorios(db: Session = Depends(get_db)):
    itens = db.scalars(select(Relatorio).order_by(Relatorio.data.desc()).limit(30)).all()
    return {"itens": [_rel(r) for r in itens], "canais": notificacoes.canais()}


@router.post("/relatorios/gerar")
def gerar(data: date | None = None, enviar: bool = False, db: Session = Depends(get_db)):
    r = relatorio.gerar(db, data or agora().date())
    envio = relatorio.enviar(db, r) if enviar else None
    return _rel(r, envio)


@router.post("/relatorios/{rel_id}/enviar")
def enviar(rel_id: int, db: Session = Depends(get_db)):
    r = db.get(Relatorio, rel_id)
    if not r:
        raise HTTPException(404, "Relatório não encontrado")
    return _rel(r, relatorio.enviar(db, r))


@router.get("/relatorios/{rel_id}/html", response_class=HTMLResponse)
def ver_html(rel_id: int, db: Session = Depends(get_db)):
    r = db.get(Relatorio, rel_id)
    if not r:
        raise HTTPException(404, "Relatório não encontrado")
    return relatorio.html(r)


@router.post("/notificacoes/teste")
def teste():
    return notificacoes.enviar("Crivo: teste de notificação",
                               "Se você recebeu esta mensagem, os alertas e o relatório diário vão chegar por aqui.",
                               "<p>Se você recebeu esta mensagem, os alertas e o relatório diário vão chegar por aqui.</p>")
