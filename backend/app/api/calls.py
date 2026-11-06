import csv
import io
from datetime import date, datetime, time, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, Response, StreamingResponse
from sqlalchemy import case, extract, func, or_, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Call
from ..services.pipeline import normalizar_tabulacao
from ..taxonomy import CATEGORIES, label_cat, label_sub

router = APIRouter(prefix="/api/v1", tags=["calls"])


def apply_filters(
    stmt,
    data_inicio: date | None = None,
    data_fim: date | None = None,
    categoria: str | None = None,
    subcategoria: str | None = None,
    telefone: str | None = None,
    operador: str | None = None,
    campanha: int | None = None,
    q: str | None = None,
    status: str | None = None,
    tronco: str | None = None,
    tipo_agente: str | None = None,
    tipo_discagem: str | None = None,
    desligado_por: str | None = None,
    divergencia: bool | None = None,
):
    if data_inicio:
        stmt = stmt.where(Call.data_ligacao >= datetime.combine(data_inicio, time.min))
    if data_fim:
        stmt = stmt.where(Call.data_ligacao < datetime.combine(data_fim + timedelta(days=1), time.min))
    if categoria:
        stmt = stmt.where(Call.categoria == categoria)
    if subcategoria:
        stmt = stmt.where(Call.subcategoria == subcategoria)
    if telefone:
        stmt = stmt.where(Call.telefone.contains(telefone))
    if operador:
        stmt = stmt.where(
            or_(
                Call.operador_nome == operador,
                Call.operador_id == operador,
                Call.operador_nome.ilike(f"%{operador}%"),
            )
        )
    if campanha:
        stmt = stmt.where(Call.id_campanha == campanha)
    if status:
        stmt = stmt.where(Call.status == status)
    if tronco:
        stmt = stmt.where(Call.tronco.ilike(f"%{tronco}%"))
    if tipo_agente:
        stmt = stmt.where(Call.tipo_agente == tipo_agente)
    if tipo_discagem:
        stmt = stmt.where(Call.tipo_discagem == tipo_discagem)
    if desligado_por:
        stmt = stmt.where(Call.desligado_por == desligado_por)
    if divergencia is not None:
        stmt = stmt.where(Call.divergencia_tabulacao.is_(divergencia))
    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            Call.nome_esperado.ilike(like)
            | Call.cliente_identificado.ilike(like)
            | Call.transcricao.ilike(like)
            | Call.telefone.contains(like)
            | Call.operador_nome.ilike(like)
            | Call.tabulacao_operador.ilike(like)
            | Call.grupo_origem.ilike(like)
        )
    return stmt


def serialize(c: Call, full: bool = False) -> dict:
    d = {
        "id": c.id,
        "id_ligacao": c.id_ligacao,
        "nr_lead": c.nr_lead,
        "id_campanha": c.id_campanha,
        "telefone": c.telefone,
        "nome_esperado": c.nome_esperado,
        "cliente_identificado": c.cliente_identificado or c.nome_esperado,
        "operador_id": c.operador_id,
        "operador_nome": c.operador_nome or "Não Identificado",
        "tabulacao_operador": c.tabulacao_operador,
        "tabulacao_normalizada": c.tabulacao_normalizada,
        "tronco": c.tronco,
        "direcionado": c.direcionado,
        "tipo_agente": c.tipo_agente,
        "tipo_discagem": c.tipo_discagem,
        "desligado_por": c.desligado_por,
        "desligamento_detalhe": c.desligamento_detalhe,
        "grupo_origem": c.grupo_origem,
        "tempo_reacao_operador": c.tempo_reacao_operador,
        "data_ligacao": c.data_ligacao.isoformat() if c.data_ligacao else None,
        "duracao_segundos": c.duracao_segundos,
        "origem": c.origem,
        "status": c.status,
        "categoria": c.categoria,
        "categoria_label": label_cat(c.categoria) if c.categoria else None,
        "subcategoria": c.subcategoria,
        "subcategoria_label": label_sub(c.categoria, c.subcategoria) if c.categoria else None,
        "confianca": c.confianca,
        "motor": c.motor,
        "resumo": c.resumo,
        "evidencia": c.evidencia,
        "sentimento_cliente": c.sentimento_cliente,
        "conflito_identidade": c.conflito_identidade,
        "divergencia_tabulacao": bool(c.divergencia_tabulacao),
        "divergencia_detalhe": c.divergencia_detalhe,
        "ligacao_referencia_id": c.ligacao_referencia_id,
        "tem_audio": bool(c.caminho_audio),
        "erro": c.erro,
    }
    if full:
        d.update(
            transcricao=c.transcricao,
            transcricao_diarizada=c.transcricao_diarizada,
            metricas_acusticas=c.metricas_acusticas,
            nome_arquivo=c.nome_arquivo,
        )
    return d


class Filtros:
    """Filtros comuns a listagem, exportação e analytics (garante que cards, gráfico e tabela batam)."""

    def __init__(
        self,
        data_inicio: date | None = None,
        data_fim: date | None = None,
        categoria: str | None = None,
        subcategoria: str | None = None,
        telefone: str | None = None,
        operador: str | None = None,
        campanha: int | None = None,
        tronco: str | None = None,
        tipo_agente: str | None = None,
        tipo_discagem: str | None = None,
        desligado_por: str | None = None,
        divergencia: bool | None = None,
        q: str | None = None,
        status: str | None = None,
    ):
        self.kw = dict(data_inicio=data_inicio, data_fim=data_fim, categoria=categoria, subcategoria=subcategoria,
                       telefone=telefone, operador=operador, campanha=campanha, q=q, status=status, tronco=tronco,
                       tipo_agente=tipo_agente, tipo_discagem=tipo_discagem, desligado_por=desligado_por,
                       divergencia=divergencia)

    def __call__(self, stmt, **override):
        return apply_filters(stmt, **{**self.kw, **override})


@router.get("/calls")
def list_calls(
    f: Filtros = Depends(),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    base = f(select(Call))
    total = db.scalar(select(func.count()).select_from(base.subquery()))
    rows = db.scalars(base.order_by(Call.data_ligacao.desc(), Call.id.desc()).offset((page - 1) * page_size).limit(page_size))
    return {"total": total, "page": page, "page_size": page_size, "items": [serialize(c) for c in rows]}


EXPORT_LIMITE = 50000


@router.get("/calls/export")
def export_calls_csv(f: Filtros = Depends(), db: Session = Depends(get_db)):
    """Exporta as ligações filtradas em CSV (';' + BOM, abre direto no Excel)."""
    rows = db.scalars(f(select(Call)).order_by(Call.data_ligacao.desc()).limit(EXPORT_LIMITE + 1)).all()
    truncado = len(rows) > EXPORT_LIMITE
    rows = rows[:EXPORT_LIMITE]

    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow([
        "ID Ligação", "Data/Hora", "Telefone", "Cliente", "Operador", "Tipo Agente", "Origem Discagem", "Tronco",
        "Desligado Por", "Sinalização SIP", "Tabulação Operador", "Categoria IA", "Subcategoria IA", "Confiança",
        "Divergência?", "Detalhe Divergência", "Duração (seg)", "Sentimento Cliente", "Status", "Resumo",
    ])
    for c in rows:
        writer.writerow([
            c.id_ligacao or c.id,
            c.data_ligacao.strftime("%d/%m/%Y %H:%M:%S") if c.data_ligacao else "",
            c.telefone or "",
            c.cliente_identificado or c.nome_esperado or "",
            c.operador_nome or "",
            c.tipo_agente or "",
            c.tipo_discagem or "",
            c.tronco or "",
            c.desligado_por or "",
            c.desligamento_detalhe or "",
            c.tabulacao_operador or "",
            label_cat(c.categoria) if c.categoria else "",
            label_sub(c.categoria, c.subcategoria) if c.categoria else "",
            f"{c.confianca:.2f}".replace(".", ",") if c.confianca is not None else "",
            "SIM" if c.divergencia_tabulacao else "NÃO",
            c.divergencia_detalhe or "",
            f"{c.duracao_segundos:.1f}".replace(".", ",") if c.duracao_segundos else "0",
            c.sentimento_cliente or "",
            c.status,
            c.resumo or "",
        ])
    return Response(
        content=output.getvalue().encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="crivo_ligacoes.csv"',
                 "X-Total-Exportado": str(len(rows)), "X-Truncado": "1" if truncado else "0"},
    )


@router.get("/calls/{call_id}")
def get_call(call_id: int, db: Session = Depends(get_db)):
    c = db.get(Call, call_id)
    if not c:
        raise HTTPException(404, "Ligação não encontrada")
    out = serialize(c, full=True)
    if c.ligacao_referencia_id and (ref := db.get(Call, c.ligacao_referencia_id)):
        out["ligacao_referencia"] = serialize(ref)
    return out


@router.get("/calls/{call_id}/audio")
def get_audio(call_id: int, db: Session = Depends(get_db)):
    c = db.get(Call, call_id)
    if not c or not c.caminho_audio or not Path(c.caminho_audio).exists():
        raise HTTPException(404, "Áudio indisponível")
    media = "audio/wav" if c.caminho_audio.lower().endswith(".wav") else "audio/mpeg"
    return FileResponse(c.caminho_audio, media_type=media)


@router.get("/taxonomy")
def taxonomy():
    return {k: {"label": v["label"], "desc": v["desc"], "subs": v["subs"]} for k, v in CATEGORIES.items()}


@router.get("/dates")
def available_dates(db: Session = Depends(get_db)):
    day = func.date(Call.data_ligacao)
    rows = db.execute(
        select(day, func.count()).where(Call.data_ligacao.is_not(None)).group_by(day).order_by(day.desc())
    ).all()
    return [{"data": str(r[0]), "total": r[1]} for r in rows if r[0]]


def _distintos(db: Session, col) -> list[dict]:
    rows = db.execute(select(col, func.count(Call.id)).where(col.is_not(None)).group_by(col)
                      .order_by(func.count(Call.id).desc())).all()
    return [{"nome": r[0], "total": r[1]} for r in rows if r[0] not in (None, "")]


@router.get("/analyst/filters-options")
def analyst_filter_options(db: Session = Depends(get_db)):
    """Opções reais (vindas do banco) para os filtros da interface."""
    return {
        "operadores": _distintos(db, Call.operador_nome),
        "troncos": _distintos(db, Call.tronco),
        "campanhas": _distintos(db, Call.id_campanha),
        "tipos_agente": [r["nome"] for r in _distintos(db, Call.tipo_agente)],
        "tipos_discagem": [r["nome"] for r in _distintos(db, Call.tipo_discagem)],
        "desligado_por": [r["nome"] for r in _distintos(db, Call.desligado_por)],
        "categorias": [{"codigo": k, "label": v["label"]} for k, v in CATEGORIES.items()],
    }


def _distribuicao(db: Session, f: Filtros, col, chave: str) -> list[dict]:
    rows = db.execute(f(select(col, func.count()).where(col.is_not(None)).group_by(col))).all()
    total = sum(n for _, n in rows)
    out = [{chave: v, "tipo": v, "total": n, "pct": round(100 * n / total, 1) if total else 0} for v, n in rows]
    return sorted(out, key=lambda x: -x["total"])


@router.get("/analytics/summary")
def summary(f: Filtros = Depends(), db: Session = Depends(get_db)):
    total = db.scalar(f(select(func.count(Call.id)))) or 0
    by_status = dict(db.execute(f(select(Call.status, func.count()).group_by(Call.status))).all())

    done = Call.status == "done"
    rows = db.execute(f(select(Call.categoria, Call.subcategoria, func.count()).where(done)
                        .group_by(Call.categoria, Call.subcategoria))).all()
    cats: dict[str, dict] = {}
    for cat, sub, n in rows:
        if not cat:
            continue
        c = cats.setdefault(cat, {"codigo": cat, "label": label_cat(cat), "total": 0, "subs": []})
        c["total"] += n
        c["subs"].append({"codigo": sub, "label": label_sub(cat, sub), "total": n})
    qualificadas = sum(c["total"] for c in cats.values())
    for c in cats.values():
        c["pct"] = round(100 * c["total"] / qualificadas, 1) if qualificadas else 0
        c["subs"].sort(key=lambda s: -s["total"])

    dur_media = db.scalar(f(select(func.avg(Call.duracao_segundos)).where(done)))
    dur_total = db.scalar(f(select(func.sum(Call.duracao_segundos)).where(done))) or 0
    conf_media = db.scalar(f(select(func.avg(Call.confianca)).where(done, Call.motor == "openai")))

    # Divergência: só faz sentido entre ligações qualificadas E tabuladas pelo operador
    comparaveis = db.scalar(f(select(func.count(Call.id)).where(done, Call.tabulacao_operador.is_not(None)))) or 0
    total_div = db.scalar(f(select(func.count(Call.id)).where(done, Call.divergencia_tabulacao.is_(True)))) or 0

    matriz_rows = db.execute(f(
        select(Call.tabulacao_operador, Call.categoria, func.count())
        .where(Call.tabulacao_operador.is_not(None))
        .group_by(Call.tabulacao_operador, Call.categoria)
    )).all()
    matriz: dict[str, dict] = {}
    for tab_op, cat_ia, n in matriz_rows:
        e = matriz.setdefault(tab_op, {"tabulacao_operador": tab_op, "esperada": normalizar_tabulacao(tab_op),
                                       "total": 0, "categorias": {}})
        e["total"] += n
        e["categorias"][cat_ia or "PENDENTE"] = n

    div_int = case((Call.divergencia_tabulacao.is_(True), 1), else_=0)
    op_rows = db.execute(f(
        select(Call.operador_nome, func.count(Call.id), func.sum(case((done, 1), else_=0)),
               func.sum(case((done, div_int), else_=0)))
        .where(Call.operador_nome.is_not(None))
        .group_by(Call.operador_nome)
        .order_by(func.count(Call.id).desc())
        .limit(15)
    )).all()
    ranking = []
    for nome, tot, qual, div in op_rows:
        qual, div = qual or 0, div or 0
        ranking.append({"operador": nome, "total": tot, "qualificadas": qual, "divergencias": div,
                        "taxa_divergencia": round(100 * div / qual, 1) if qual else 0})

    return {
        "total": total,
        "qualificadas": qualificadas,
        "status": by_status,
        "duracao_media": round(dur_media or 0, 1),
        "duracao_total_horas": round(dur_total / 3600, 2),
        "confianca_media": round(conf_media, 2) if conf_media is not None else None,
        "conflitos_identidade": db.scalar(f(select(func.count(Call.id)).where(Call.conflito_identidade.is_(True)))) or 0,
        "desligamentos": _distribuicao(db, f, Call.desligado_por, "tipo"),
        "agentes": _distribuicao(db, f, Call.tipo_agente, "tipo"),
        "discagens": _distribuicao(db, f, Call.tipo_discagem, "tipo"),
        "troncos": _distribuicao(db, f, Call.tronco, "tronco"),
        "divergencias": {"total": total_div, "comparaveis": comparaveis,
                         "taxa": round(100 * total_div / comparaveis, 1) if comparaveis else 0},
        "matriz_contraste": sorted(matriz.values(), key=lambda x: -x["total"])[:15],
        "ranking_operadores": ranking,
        "categorias": sorted(cats.values(), key=lambda c: -c["total"]),
    }


@router.get("/analytics/timeline")
def timeline(f: Filtros = Depends(), db: Session = Depends(get_db)):
    """Volume diário por categoria, com os MESMOS filtros dos cards e da tabela."""
    day = func.date(Call.data_ligacao)
    stmt = f(select(day, Call.categoria, func.count()).where(Call.status == "done", Call.data_ligacao.is_not(None)))
    out: dict[str, dict] = {}
    for d, cat, n in db.execute(stmt.group_by(day, Call.categoria)).all():
        out.setdefault(str(d), {"data": str(d)})[cat] = n
    return sorted(out.values(), key=lambda x: x["data"])


@router.get("/analytics/horas")
def por_hora(f: Filtros = Depends(), db: Session = Depends(get_db)):
    """Distribuição por hora do dia × categoria (mapa de calor de contato)."""
    hora = extract("hour", Call.data_ligacao)
    stmt = f(select(hora, Call.categoria, func.count()).where(Call.status == "done", Call.data_ligacao.is_not(None)))
    out = {h: {"hora": h} for h in range(24)}
    for h, cat, n in db.execute(stmt.group_by(hora, Call.categoria)).all():
        if h is not None and cat:
            out[int(h)][cat] = n
    return list(out.values())
