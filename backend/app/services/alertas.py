"""Alertas automáticos: avaliados periodicamente, guardados com histórico e notificados quando abrem.

Regras (limites no .env, ver config.py):
- operador: taxa de divergência alta numa janela (crítico com muitas divergências de gravidade alta);
- tronco: pico de ligações mudas num tronco, bem acima dos outros (sinal de problema na linha);
- nao_ligar: pedido de "não ligar" sem registro na tabulação (LGPD);
- sistema: alertas CRÍTICOS da saúde do sistema (integração caída, teto de IA...).

Um alerta fica aberto enquanto a condição durar e é resolvido sozinho quando ela some.
A notificação sai quando o alerta abre (ou piora para crítico), no máximo a cada ALERTA_RENOTIFICAR_HORAS.
"""
import logging
from datetime import datetime, timedelta
from urllib.parse import urlencode

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Alerta, Call, agora
from . import notificacoes

log = logging.getLogger("alertas")

REGRAS = {
    "operador": "Operador com taxa de divergência alta",
    "tronco": "Pico de ligações mudas num tronco",
    "nao_ligar": "Pedido de não ligar sem registro (LGPD)",
    "sistema": "Falha crítica do sistema",
}


def _link(caminho: str, **filtros) -> str:
    q = urlencode({k: v for k, v in filtros.items() if v not in (None, "")})
    return f"{caminho}?{q}" if q else caminho


def _janela(horas: int) -> str:
    return f"nos últimos {horas // 24} dias" if horas >= 48 and horas % 24 == 0 else f"nas últimas {horas}h"


def _pct(a: float, b: float) -> float:
    return 100 * a / b if b else 0.0


def _condicoes(db: Session, t: datetime) -> list[dict]:
    out: list[dict] = []
    done = Call.status == "done"

    # ---- operadores
    ini = t - timedelta(hours=settings.alerta_operador_horas)
    rows = db.execute(
        select(Call.operador_nome, func.count(Call.id),
               func.sum(case((Call.divergencia_tabulacao.is_(True), 1), else_=0)),
               func.sum(case((Call.divergencia_gravidade == "alta", 1), else_=0)))
        .where(done, Call.operador_nome.is_not(None), Call.data_ligacao >= ini, Call.data_ligacao <= t)
        .group_by(Call.operador_nome)
    ).all()
    for nome, n, div, altas in rows:
        div, altas = div or 0, altas or 0
        taxa = _pct(div, n)
        if n < settings.alerta_operador_min_ligacoes:
            continue
        critico = altas >= settings.alerta_operador_altas
        if taxa < settings.alerta_operador_taxa and not critico:
            continue
        out.append({
            "chave": f"operador:{nome}", "tipo": "operador", "nivel": "critico" if critico else "atencao",
            "titulo": f"Divergência alta: {nome}", "valor": round(taxa, 1),
            "mensagem": (f"{nome}: {div} de {n} ligações qualificadas divergentes ({taxa:.0f}%), {altas} de gravidade "
                         f"alta, {_janela(settings.alerta_operador_horas)}."),
            "link": _link("/ligacoes", operador=nome, divergencia="true", data_inicio=ini.date().isoformat()),
        })

    # ---- troncos
    ini = t - timedelta(hours=settings.alerta_tronco_horas)
    rows = db.execute(
        select(Call.tronco, func.count(Call.id), func.sum(case((Call.categoria == "LIGACAO_MUDA", 1), else_=0)))
        .where(done, Call.tronco.is_not(None), Call.data_ligacao >= ini, Call.data_ligacao <= t)
        .group_by(Call.tronco)
    ).all()
    tot_n = sum(r[1] for r in rows)
    tot_m = sum(r[2] or 0 for r in rows)
    for tronco, n, mudas in rows:
        mudas = mudas or 0
        pct = _pct(mudas, n)
        resto_n, resto_m = tot_n - n, tot_m - mudas
        pct_resto = _pct(resto_m, resto_n) if resto_n else None
        if n < settings.alerta_tronco_min_ligacoes or pct < settings.alerta_tronco_mudas_pct:
            continue
        if pct_resto is not None and pct < 1.5 * pct_resto:  # todos os troncos estão assim: não é o tronco
            continue
        comp = f", contra {pct_resto:.0f}% nos outros troncos" if pct_resto is not None else ""
        out.append({
            "chave": f"tronco:{tronco}", "tipo": "tronco", "nivel": "critico" if pct >= 70 else "atencao",
            "titulo": f"Muitas ligações mudas: {tronco}", "valor": round(pct, 1),
            "mensagem": (f"{mudas} de {n} ligações do tronco {tronco} foram mudas ({pct:.0f}%{comp}) "
                         f"{_janela(settings.alerta_tronco_horas)}. Pode ser problema na linha."),
            "link": _link("/ligacoes", tronco=tronco, categoria="LIGACAO_MUDA", data_inicio=ini.date().isoformat()),
        })

    # ---- pedidos de não ligar sem registro (LGPD)
    ini = t - timedelta(hours=24)
    n = db.scalar(select(func.count(Call.id)).where(
        done, Call.pediu_nao_ligar.is_(True), Call.divergencia_tabulacao.is_(True),
        Call.divergencia_detalhe.like("%não ligar%"), Call.data_ligacao >= ini, Call.data_ligacao <= t)) or 0
    if n:
        out.append({
            "chave": "nao_ligar", "tipo": "nao_ligar", "nivel": "atencao", "valor": n,
            "titulo": "Pedidos de não ligar sem registro (LGPD)",
            "mensagem": f"{n} cliente(s) pediram para não receber mais ligações nas últimas 24h e a tabulação não "
                        "registrou o pedido. Confira se os números saíram do mailing.",
            "link": _link("/ligacoes", nao_ligar="true", divergencia="true"),
        })

    # ---- sistema: só os críticos da tela de saúde
    try:
        from ..api.saude import saude

        for a in saude(db)["alertas"]:
            if a["nivel"] == "critico":
                out.append({"chave": f"sistema:{a['titulo']}", "tipo": "sistema", "nivel": "critico",
                            "titulo": a["titulo"], "mensagem": a["mensagem"], "link": "/saude", "valor": None})
    except Exception:  # pragma: no cover - a saúde nunca deve derrubar os alertas de negócio
        log.exception("falha ao ler a saúde do sistema")
    return out


def avaliar(db: Session, t: datetime | None = None, notificar: bool = True) -> dict:
    """Abre, atualiza e resolve alertas conforme as condições atuais. Notifica os que abriram/pioraram."""
    t = t or agora()
    atuais = {c["chave"]: c for c in _condicoes(db, t)}
    abertos = {a.chave: a for a in db.scalars(select(Alerta).where(Alerta.resolvido_em.is_(None)))}
    novos, piorou, resolvidos = [], [], 0

    for chave, c in atuais.items():
        a = abertos.get(chave)
        if a is None:
            a = Alerta(chave=chave, tipo=c["tipo"], nivel=c["nivel"], titulo=c["titulo"], mensagem=c["mensagem"],
                       link=c["link"], valor=c["valor"], aberto_em=t, atualizado_em=t)
            db.add(a)
            novos.append(a)
            continue
        if a.nivel == "atencao" and c["nivel"] == "critico":
            piorou.append(a)
        a.nivel, a.titulo, a.mensagem, a.link, a.valor, a.atualizado_em = (
            c["nivel"], c["titulo"], c["mensagem"], c["link"], c["valor"], t)
    for chave, a in abertos.items():
        if chave not in atuais:
            a.resolvido_em = t
            resolvidos += 1
    db.flush()

    avisar = []
    for a in novos + piorou:
        ultimo = db.scalar(select(func.max(Alerta.notificado_em)).where(Alerta.chave == a.chave, Alerta.id != a.id))
        recente = ultimo and t - ultimo < timedelta(hours=settings.alerta_renotificar_horas)
        if not recente or a in piorou:
            avisar.append(a)
    envio = None
    if notificar and avisar:
        envio = notificacoes.enviar(*_mensagem(avisar))
        for a in avisar:
            a.notificado_em = t
    db.commit()
    return {"novos": len(novos), "resolvidos": resolvidos, "abertos": len(atuais), "notificados": len(avisar),
            "envio": envio}


def _mensagem(alertas: list[Alerta]) -> tuple[str, str, str]:
    crit = sum(a.nivel == "critico" for a in alertas)
    assunto = f"Crivo: {len(alertas)} alerta(s)" + (f", {crit} crítico(s)" if crit else "")
    linhas, html = [], []
    for a in sorted(alertas, key=lambda x: x.nivel != "critico"):
        icone = "🔴" if a.nivel == "critico" else "🟠"
        link = notificacoes.link(a.link)
        linhas.append(f"{icone} {a.titulo}\n{a.mensagem}" + (f"\n{link}" if link else ""))
        html.append(f"<p><b>{icone} {a.titulo}</b><br>{a.mensagem}"
                    + (f'<br><a href="{link}">Abrir no painel</a>' if link.startswith("http") else "") + "</p>")
    return assunto, "\n\n".join(linhas), "".join(html)


def serializar(a: Alerta) -> dict:
    iso = lambda d: d.isoformat() if d else None  # noqa: E731
    return {"id": a.id, "chave": a.chave, "tipo": a.tipo, "nivel": a.nivel, "titulo": a.titulo, "mensagem": a.mensagem,
            "link": a.link, "valor": a.valor, "aberto_em": iso(a.aberto_em), "atualizado_em": iso(a.atualizado_em),
            "resolvido_em": iso(a.resolvido_em), "notificado_em": iso(a.notificado_em),
            "reconhecido_por": a.reconhecido_por, "reconhecido_em": iso(a.reconhecido_em)}
