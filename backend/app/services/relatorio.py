"""Relatório diário: resumo do dia para quem não abre o painel (enviado por webhook/e-mail).

Gerado sozinho a partir de RELATORIO_HORA nos dias de RELATORIO_DIAS; pode ser gerado à mão pela tela.
"""
from datetime import date, datetime, time, timedelta
from html import escape

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import (Alerta, Avaliacao, AvaliacaoCiencia, Call, PontoImportacao, PontoJornada, Relatorio,
                      agora)
from . import notificacoes


def _dias_permitidos() -> set[int]:
    out: set[int] = set()
    for parte in settings.relatorio_dias.split(","):
        parte = parte.strip()
        if "-" in parte:
            a, b = (int(x) for x in parte.split("-"))
            out.update(range(a, b + 1))
        elif parte.isdigit():
            out.add(int(parte))
    return out


def deve_gerar(t: datetime, ultimo: date | None) -> bool:
    """Já passou da hora do relatório, hoje é dia de relatório e ele ainda não foi gerado?"""
    return t.weekday() in _dias_permitidos() and t.hour >= settings.relatorio_hora and ultimo != t.date()


def gerar(db: Session, dia: date) -> Relatorio:
    from ..api.calls import Filtros, summary

    s = summary(f=Filtros(data_inicio=dia, data_fim=dia), db=db)
    ini, fim = datetime.combine(dia, time.min), datetime.combine(dia + timedelta(days=1), time.min)
    operadores = sorted((o for o in s["ranking_operadores"] if o["qualificadas"] >= 5 or o["divergencias"]),
                        key=lambda o: (-o["divergencias"], -o["taxa_divergencia"]))[:5]
    altas_op = dict(db.execute(select(Call.operador_nome, func.count(Call.id)).where(
        Call.data_ligacao >= ini, Call.data_ligacao < fim, Call.status == "avaliada", Call.divergencia_gravidade == "alta")
        .group_by(Call.operador_nome)).all())
    for o in operadores:
        o["altas"] = altas_op.get(o["operador"], 0)
    mudas = {c["codigo"]: c for c in s["categorias"]}.get("LIGACAO_MUDA")
    dados = {
        "data": dia.isoformat(),
        "total": s["total"],
        "qualificadas": s["qualificadas"],
        "nao_avaliadas": s["nao_avaliadas"],
        "divergencias": s["divergencias"],
        "categorias": [{"codigo": c["codigo"], "label": c["label"], "total": c["total"], "pct": c["pct"]} for c in s["categorias"]],
        "mudas_pct": mudas["pct"] if mudas else 0,
        "operadores": operadores,
        "troncos": s["troncos"][:5],
        "nao_ligar": s["nao_ligar"],
        "aguardando_avaliacao": db.scalar(select(func.count(Call.id)).where(Call.status == "pendente_avaliacao")) or 0,
        "avaliadas_no_dia": db.scalar(select(func.count(Avaliacao.id)).where(
            Avaliacao.status.in_(("finalizada", "nao_avaliavel")), Avaliacao.finalizada_em >= ini,
            Avaliacao.finalizada_em < fim)) or 0,
        "monitoria": _monitoria(db, ini, fim),
        "ponto": _ponto(db, dia),
        "alertas_abertos": [{"nivel": a.nivel, "titulo": a.titulo, "mensagem": a.mensagem}
                            for a in db.scalars(select(Alerta).where(Alerta.resolvido_em.is_(None))
                                                .order_by(Alerta.nivel, Alerta.aberto_em))],
    }
    rel = db.scalars(select(Relatorio).where(Relatorio.data == dia)).first() or Relatorio(data=dia)
    rel.dados, rel.texto, rel.gerado_em = dados, texto(dados), agora()
    rel.enviado_em = rel.envio_detalhe = None
    db.add(rel)
    db.commit()
    return rel


def _monitoria(db: Session, ini: datetime, fim: datetime) -> dict:
    """Avaliações do script finalizadas no dia."""
    from .supervisao import ciencias

    avs = db.scalars(select(Avaliacao).where(Avaliacao.status == "finalizada", Avaliacao.script_versao_id.is_not(None),
                                             Avaliacao.finalizada_em >= ini, Avaliacao.finalizada_em < fim)).all()
    notas = [a.nota for a in avs if a.nota is not None]
    cien = ciencias(db, [a.id for a in avs])
    sem_ciencia_total = db.scalar(select(func.count(Avaliacao.id)).where(
        Avaliacao.status == "finalizada", Avaliacao.script_versao_id.is_not(None),
        Avaliacao.id.not_in(select(AvaliacaoCiencia.avaliacao_id)))) or 0
    return {"avaliacoes": len(avs), "nota_media": round(sum(notas) / len(notas), 1) if notas else None,
            "falhas_criticas": sum(1 for a in avs if a.falha_critica), "com_ciencia": len(cien),
            "sem_ciencia_total": sem_ciencia_total}


def _ponto(db: Session, dia: date) -> dict | None:
    """Ponto do dia, se importado (completo quando as pausas do dia também foram)."""
    from . import ponto

    if not db.scalar(select(func.count(PontoJornada.id)).where(PontoJornada.data == dia)):
        return None
    completo = bool(db.scalar(select(func.count(PontoImportacao.id)).where(
        PontoImportacao.tipo == "pausas", PontoImportacao.data_ref == dia)))
    linhas = ponto.relatorio(db, dia, completo)
    r = ponto.resumo(linhas, completo)
    r["completo"] = completo
    r["atrasados"] = [{"operador": v.operador, "minutos": v.atraso_min} for v in linhas if v.atraso_min][:10]
    return r


def _br(n: float, casas: int = 0) -> str:
    return f"{n:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _dia(d: str) -> str:
    return date.fromisoformat(d).strftime("%d/%m/%Y")


def assunto(rel: Relatorio) -> str:
    return f"Crivo: relatório de {_dia(rel.dados['data'])}"


def texto(d: dict) -> str:
    div = d["divergencias"]
    g = div["por_gravidade"]
    linhas = [
        f"📞 {_br(d['total'])} ligações · {_br(d['qualificadas'])} avaliadas · {_br(d.get('nao_avaliadas', 0))} não avaliadas",
        f"⚠️ Divergência de tabulação: {_br(div['taxa'], 1)}% ({_br(div['total'])}: {g.get('alta', 0)} alta, "
        f"{g.get('media', 0)} média, {g.get('baixa', 0)} baixa)",
        f"🔇 Ligações mudas: {_br(d['mudas_pct'], 1)}%",
    ]
    if d["nao_ligar"]:
        linhas.append(f"🚫 Pedidos de não ligar (LGPD): {_br(d['nao_ligar'])}")
    if d["operadores"]:
        linhas.append("\nOperadores com mais divergências:")
        linhas += [f"• {o['operador']}: {o['divergencias']} de {o['qualificadas']} ({_br(o['taxa_divergencia'], 0)}%)"
                   + (f", {o['altas']} alta(s)" if o["altas"] else "") for o in d["operadores"]]
    linhas.append(f"\n👂 Aguardando avaliação: {_br(d['aguardando_avaliacao'])} · "
                  f"avaliadas pela monitoria no dia: {_br(d['avaliadas_no_dia'])}")
    m = d.get("monitoria")
    if m and m["avaliacoes"]:
        linhas.append(f"🎧 Script: {_br(m['avaliacoes'])} avaliações · nota média "
                      f"{_br(m['nota_media'], 1) if m['nota_media'] is not None else '–'} · "
                      f"{_br(m['falhas_criticas'])} com falha crítica · {_br(m['sem_ciencia_total'])} aguardando ciência")
    p = d.get("ponto")
    if p:
        extra = (f" · almoço médio {_br((p['almoco_medio_seg'] or 0) / 60)} min · {_br(p['almoco_acima_1h'] or 0)} acima de 1h"
                 if p.get("completo") else "")
        linhas.append(f"🕘 Ponto: {_br(p['presentes'])} presentes · {_br(p['atrasos'])} atraso(s){extra}")
        linhas += [f"   • {a['operador']}: {a['minutos']} min" for a in p["atrasados"]]
    if d["alertas_abertos"]:
        linhas.append("\nAlertas abertos:")
        linhas += [f"{'🔴' if a['nivel'] == 'critico' else '🟠'} {a['titulo']}" for a in d["alertas_abertos"]]
    painel = notificacoes.link("/")
    if painel.startswith("http"):
        linhas.append(f"\nPainel: {painel}")
    return "\n".join(linhas)


def html(rel: Relatorio) -> str:
    """Versão para e-mail (estilos inline; clientes de e-mail ignoram CSS externo)."""
    d = rel.dados
    div = d["divergencias"]
    td = 'style="padding:6px 10px;border-bottom:1px solid #e1e0d9"'
    num = 'style="padding:6px 10px;border-bottom:1px solid #e1e0d9;text-align:right"'
    kpis = [("Ligações", _br(d["total"])), ("Avaliadas", _br(d["qualificadas"])),
            ("Não avaliadas", _br(d.get("nao_avaliadas", 0))), ("Divergência", f"{_br(div['taxa'], 1)}%"),
            ("Mudas", f"{_br(d['mudas_pct'], 1)}%"), ("Não ligar", _br(d["nao_ligar"]))]
    ops = "".join(f"<tr><td {td}>{escape(o['operador'])}</td><td {num}>{o['divergencias']} de {o['qualificadas']}</td>"
                  f"<td {num}>{_br(o['taxa_divergencia'], 0)}%</td><td {num}>{o['altas']}</td></tr>" for o in d["operadores"])
    cats = "".join(f"<tr><td {td}>{escape(c['label'])}</td><td {num}>{_br(c['total'])}</td><td {num}>{_br(c['pct'], 1)}%</td></tr>"
                   for c in d["categorias"])
    alertas = "".join(f"<li>{'🔴' if a['nivel'] == 'critico' else '🟠'} <b>{escape(a['titulo'])}</b><br>{escape(a['mensagem'])}</li>"
                      for a in d["alertas_abertos"])
    g = div["por_gravidade"]
    return f"""<!doctype html><html><body style="margin:0;background:#f9f9f7;font-family:system-ui,-apple-system,'Segoe UI',sans-serif;color:#0b0b0b">
<div style="max-width:640px;margin:0 auto;padding:24px">
<h1 style="font-size:20px;margin:0 0 4px">Crivo · relatório de {_dia(d['data'])}</h1>
<p style="color:#52514e;margin:0 0 16px">Tabulação do operador × resultado da monitoria</p>
<table style="width:100%;border-collapse:collapse;background:#fff;border:1px solid #e1e0d9;border-radius:12px"><tr>
{''.join(f'<td style="padding:12px;text-align:center"><div style="font-size:12px;color:#52514e">{k}</div><div style="font-size:20px;font-weight:600">{v}</div></td>' for k, v in kpis)}
</tr></table>
<p style="margin:16px 0 4px;color:#52514e">Divergências por gravidade: <b>{g.get('alta', 0)} alta</b> · {g.get('media', 0)} média · {g.get('baixa', 0)} baixa</p>
<h2 style="font-size:15px;margin:20px 0 6px">Operadores com mais divergências</h2>
<table style="width:100%;border-collapse:collapse;background:#fff"><tr><th {td} align="left">Operador</th><th {num}>Divergentes</th><th {num}>Taxa</th><th {num}>Altas</th></tr>{ops or f'<tr><td {td} colspan="4">Nenhum</td></tr>'}</table>
<h2 style="font-size:15px;margin:20px 0 6px">Resultado das ligações avaliadas</h2>
<table style="width:100%;border-collapse:collapse;background:#fff"><tr><th {td} align="left">Categoria</th><th {num}>Ligações</th><th {num}>%</th></tr>{cats}</table>
{f'<h2 style="font-size:15px;margin:20px 0 6px">Alertas abertos</h2><ul>{alertas}</ul>' if alertas else ''}
{_html_monitoria_ponto(d, td, num)}
<p style="color:#52514e;font-size:13px;margin-top:20px">Aguardando avaliação: {_br(d.get('aguardando_avaliacao', d.get('fila_revisao', 0)))} · avaliadas no dia: {_br(d.get('avaliadas_no_dia', d.get('revisadas_no_dia', 0)))}</p>
</div></body></html>"""


def _html_monitoria_ponto(d: dict, td: str, num: str) -> str:
    out = ""
    m = d.get("monitoria")
    if m and m["avaliacoes"]:
        nota = _br(m["nota_media"], 1) if m["nota_media"] is not None else "–"
        out += (f'<h2 style="font-size:15px;margin:20px 0 6px">Monitoria do script</h2><table style="width:100%;border-collapse:collapse;background:#fff">'
                f'<tr><td {td}>Avaliações no dia</td><td {num}>{_br(m["avaliacoes"])}</td></tr>'
                f'<tr><td {td}>Nota média</td><td {num}>{nota}</td></tr>'
                f'<tr><td {td}>Com falha crítica</td><td {num}>{_br(m["falhas_criticas"])}</td></tr>'
                f'<tr><td {td}>Aguardando ciência do supervisor (total)</td><td {num}>{_br(m["sem_ciencia_total"])}</td></tr></table>')
    p = d.get("ponto")
    if p:
        linhas = (f'<tr><td {td}>Presentes</td><td {num}>{_br(p["presentes"])}</td></tr>'
                  f'<tr><td {td}>Atrasos</td><td {num}>{_br(p["atrasos"])}</td></tr>')
        if p.get("completo"):
            linhas += (f'<tr><td {td}>Almoço médio</td><td {num}>{_br((p["almoco_medio_seg"] or 0) / 60)} min</td></tr>'
                       f'<tr><td {td}>Almoço acima de 1h</td><td {num}>{_br(p["almoco_acima_1h"] or 0)}</td></tr>')
        linhas += "".join(f'<tr><td {td}>⏰ {escape(a["operador"])}</td><td {num}>{a["minutos"]} min de atraso</td></tr>'
                          for a in p["atrasados"])
        out += (f'<h2 style="font-size:15px;margin:20px 0 6px">Ponto</h2>'
                f'<table style="width:100%;border-collapse:collapse;background:#fff">{linhas}</table>')
    return out


def enviar(db: Session, rel: Relatorio) -> dict:
    r = notificacoes.enviar(assunto(rel), rel.texto, html(rel))
    rel.envio_detalhe = r.get("motivo") or ("; ".join(f"{k}: {v}" for k, v in r.get("erros", {}).items()) or None)
    if r.get("enviado"):
        rel.enviado_em = agora()
    db.commit()
    return r


def ultimo_gerado(db: Session) -> date | None:
    return db.scalar(select(func.max(Relatorio.data)))
