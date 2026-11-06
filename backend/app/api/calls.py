import csv
import io
from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, Response, StreamingResponse
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Call
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


@router.get("/calls")
def list_calls(
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
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    base = apply_filters(
        select(Call),
        data_inicio,
        data_fim,
        categoria,
        subcategoria,
        telefone,
        operador,
        campanha,
        q,
        status,
        tronco=tronco,
        tipo_agente=tipo_agente,
        tipo_discagem=tipo_discagem,
        desligado_por=desligado_por,
        divergencia=divergencia,
    )
    total = db.scalar(select(func.count()).select_from(base.subquery()))
    rows = db.scalars(
        base.order_by(Call.data_ligacao.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    return {"total": total, "page": page, "page_size": page_size, "items": [serialize(c) for c in rows]}


@router.get("/calls/export")
def export_calls_csv(
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
    db: Session = Depends(get_db),
):
    """Exporta todas as ligações filtradas em formato CSV estruturado para análise em Excel/BI."""
    base = apply_filters(
        select(Call),
        data_inicio,
        data_fim,
        categoria,
        subcategoria,
        telefone,
        operador,
        campanha,
        q,
        None,
        tronco=tronco,
        tipo_agente=tipo_agente,
        tipo_discagem=tipo_discagem,
        desligado_por=desligado_por,
        divergencia=divergencia,
    )
    rows = db.scalars(base.order_by(Call.data_ligacao.desc()).limit(10000)).all()

    output = io.StringIO()
    # UTF-8 BOM para abrir perfeitamente no Excel brasileiro
    output.write("\ufeff")
    writer = csv.writer(output, delimiter=";")

    writer.writerow([
        "ID Ligação",
        "Data/Hora",
        "Telefone",
        "Cliente",
        "Operador",
        "Tipo Agente",
        "Origem Discagem",
        "Tronco",
        "Desligado Por",
        "Sinalização SIP",
        "Tabulação Operador",
        "Categoria IA",
        "Subcategoria IA",
        "Divergência?",
        "Detalhe Divergência",
        "Duração (seg)",
        "Sentimento Cliente",
        "Status",
        "Resumo",
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
            "SIM" if c.divergencia_tabulacao else "NÃO",
            c.divergencia_detalhe or "",
            f"{c.duracao_segundos:.1f}" if c.duracao_segundos else "0",
            c.sentimento_cliente or "",
            c.status,
            c.resumo or "",
        ])

    csv_data = output.getvalue().encode("utf-8-sig")
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="auditoria_ligacoes.csv"'},
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
    if not c or not c.caminho_audio:
        raise HTTPException(404, "Áudio indisponível")
    return FileResponse(c.caminho_audio, media_type="audio/mpeg")


@router.get("/taxonomy")
def taxonomy():
    return {k: {"label": v["label"], "desc": v["desc"], "subs": v["subs"]} for k, v in CATEGORIES.items()}


@router.get("/dates")
def available_dates(db: Session = Depends(get_db)):
    day = func.date(Call.data_ligacao)
    rows = db.execute(
        select(day, func.count())
        .where(Call.data_ligacao.is_not(None))
        .group_by(day)
        .order_by(day.desc())
    ).all()
    return [{"data": str(r[0]), "total": r[1]} for r in rows if r[0]]


@router.get("/analyst/filters-options")
def analyst_filter_options(db: Session = Depends(get_db)):
    """Retorna opções disponíveis para todos os dropdowns de filtro do analista."""
    op_rows = (
        db.execute(
            select(Call.operador_nome, func.count(Call.id))
            .where(Call.operador_nome.is_not(None))
            .group_by(Call.operador_nome)
            .order_by(func.count(Call.id).desc())
        )
        .all()
    )
    operadores = [{"nome": r[0], "total": r[1]} for r in op_rows if r[0]]

    tr_rows = (
        db.execute(
            select(Call.tronco, func.count(Call.id))
            .where(Call.tronco.is_not(None))
            .group_by(Call.tronco)
            .order_by(func.count(Call.id).desc())
        )
        .all()
    )
    troncos = [{"nome": r[0], "total": r[1]} for r in tr_rows if r[0]]

    return {
        "operadores": operadores,
        "troncos": troncos,
        "tipos_agente": ["COMERCIAL", "DIGITAL"],
        "tipos_discagem": ["ATIVO", "URA"],
        "desligado_por": ["CLIENTE", "OPERADOR"],
        "categorias": [{"codigo": k, "label": v["label"]} for k, v in CATEGORIES.items()],
    }


@router.get("/analytics/summary")
def summary(
    data_inicio: date | None = None,
    data_fim: date | None = None,
    categoria: str | None = None,
    operador: str | None = None,
    campanha: int | None = None,
    tronco: str | None = None,
    tipo_agente: str | None = None,
    tipo_discagem: str | None = None,
    desligado_por: str | None = None,
    divergencia: bool | None = None,
    q: str | None = None,
    db: Session = Depends(get_db),
):
    def f(s):
        return apply_filters(
            s,
            data_inicio=data_inicio,
            data_fim=data_fim,
            categoria=categoria,
            operador=operador,
            campanha=campanha,
            tronco=tronco,
            tipo_agente=tipo_agente,
            tipo_discagem=tipo_discagem,
            desligado_por=desligado_por,
            divergencia=divergencia,
            q=q,
        )

    total = db.scalar(f(select(func.count(Call.id)))) or 0
    by_status = dict(db.execute(f(select(Call.status, func.count()).group_by(Call.status))).all())

    # Categorias e Subcategorias
    rows = db.execute(
        f(
            select(Call.categoria, Call.subcategoria, func.count())
            .where(Call.status == "done")
            .group_by(Call.categoria, Call.subcategoria)
        )
    ).all()
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

    dur_media = db.scalar(f(select(func.avg(Call.duracao_segundos)).where(Call.status == "done")))
    dur_total = db.scalar(f(select(func.sum(Call.duracao_segundos)).where(Call.status == "done"))) or 0

    # Desligado por (CLIENTE vs OPERADOR)
    desligado_rows = db.execute(
        f(select(Call.desligado_por, func.count()).where(Call.desligado_por.is_not(None)).group_by(Call.desligado_por))
    ).all()
    desligamentos = []
    total_deslig = sum(r[1] for r in desligado_rows)
    for d_tipo, d_n in desligado_rows:
        pct = round(100 * d_n / total_deslig, 1) if total_deslig else 0
        desligamentos.append({"tipo": d_tipo, "total": d_n, "pct": pct})
    desligamentos.sort(key=lambda x: -x["total"])

    # Tipo Agente (COMERCIAL vs DIGITAL)
    agente_rows = db.execute(
        f(select(Call.tipo_agente, func.count()).where(Call.tipo_agente.is_not(None)).group_by(Call.tipo_agente))
    ).all()
    agentes = []
    total_ag = sum(r[1] for r in agente_rows)
    for ag_tipo, ag_n in agente_rows:
        pct = round(100 * ag_n / total_ag, 1) if total_ag else 0
        agentes.append({"tipo": ag_tipo, "total": ag_n, "pct": pct})
    agentes.sort(key=lambda x: -x["total"])

    # Tipo Discagem (ATIVO vs URA)
    disc_rows = db.execute(
        f(select(Call.tipo_discagem, func.count()).where(Call.tipo_discagem.is_not(None)).group_by(Call.tipo_discagem))
    ).all()
    discagens = []
    total_disc = sum(r[1] for r in disc_rows)
    for disc_tipo, disc_n in disc_rows:
        pct = round(100 * disc_n / total_disc, 1) if total_disc else 0
        discagens.append({"tipo": disc_tipo, "total": disc_n, "pct": pct})
    discagens.sort(key=lambda x: -x["total"])

    # Troncos
    tronco_rows = db.execute(
        f(select(Call.tronco, func.count()).where(Call.tronco.is_not(None)).group_by(Call.tronco))
    ).all()
    troncos_list = []
    for tr_name, tr_count in tronco_rows:
        tr_pct = round(100 * tr_count / total, 1) if total else 0
        troncos_list.append({"tronco": tr_name, "total": tr_count, "pct": tr_pct})
    troncos_list.sort(key=lambda x: -x["total"])

    # Divergências de Tabulação (Operador vs IA)
    total_divergencias = db.scalar(
        f(select(func.count(Call.id)).where(Call.divergencia_tabulacao.is_(True)))
    ) or 0
    taxa_divergencia = round(100 * total_divergencias / qualificadas, 1) if qualificadas else 0

    # Matriz de Contraste: Tabulação Operador vs Categoria IA
    matriz_rows = db.execute(
        f(
            select(Call.tabulacao_operador, Call.categoria, func.count())
            .where(Call.tabulacao_operador.is_not(None))
            .group_by(Call.tabulacao_operador, Call.categoria)
            .order_by(func.count().desc())
        )
    ).all()
    matriz: dict[str, dict] = {}
    for tab_op, cat_ia, n in matriz_rows:
        entry = matriz.setdefault(
            tab_op,
            {"tabulacao_operador": tab_op, "total": 0, "categorias": {}},
        )
        entry["total"] += n
        cat_key = cat_ia or "PENDENTE"
        entry["categorias"][cat_key] = n

    matriz_list = sorted(matriz.values(), key=lambda x: -x["total"])[:15]

    # Ranking de Operadores e taxa de divergência
    op_ranking_rows = db.execute(
        f(
            select(
                Call.operador_nome,
                func.count(Call.id).label("total"),
                func.sum(case((Call.divergencia_tabulacao.is_(True), 1), else_=0)).label("divergencias"),
            )
            .where(Call.operador_nome.is_not(None))
            .group_by(Call.operador_nome)
            .order_by(func.count(Call.id).desc())
            .limit(10)
        )
    ).all()

    ranking_operadores = []
    for r_nome, r_total, r_div in op_ranking_rows:
        r_div = r_div or 0
        r_taxa = round(100 * r_div / r_total, 1) if r_total else 0
        ranking_operadores.append(
            {
                "operador": r_nome,
                "total": r_total,
                "divergencias": r_div,
                "taxa_divergencia": r_taxa,
            }
        )

    return {
        "total": total,
        "qualificadas": qualificadas,
        "status": by_status,
        "duracao_media": round(dur_media or 0, 1),
        "duracao_total_horas": round(dur_total / 3600, 2),
        "conflitos_identidade": db.scalar(f(select(func.count(Call.id)).where(Call.conflito_identidade.is_(True)))) or 0,
        "desligamentos": desligamentos,
        "agentes": agentes,
        "discagens": discagens,
        "troncos": troncos_list,
        "divergencias": {
            "total": total_divergencias,
            "taxa": taxa_divergencia,
        },
        "matriz_contraste": matriz_list,
        "ranking_operadores": ranking_operadores,
        "categorias": sorted(cats.values(), key=lambda c: -c["total"]),
    }


@router.get("/analytics/timeline")
def timeline(
    data_inicio: date | None = None,
    data_fim: date | None = None,
    tronco: str | None = None,
    tipo_agente: str | None = None,
    tipo_discagem: str | None = None,
    desligado_por: str | None = None,
    db: Session = Depends(get_db),
):
    day = func.date(Call.data_ligacao)
    stmt = select(day, Call.categoria, func.count()).where(Call.status == "done", Call.data_ligacao.is_not(None))
    stmt = apply_filters(
        stmt,
        data_inicio,
        data_fim,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        tronco=tronco,
        tipo_agente=tipo_agente,
        tipo_discagem=tipo_discagem,
        desligado_por=desligado_por,
    )
    out: dict[str, dict] = {}
    for d, cat, n in db.execute(stmt.group_by(day, Call.categoria)).all():
        out.setdefault(str(d), {"data": str(d)})[cat] = n
    return sorted(out.values(), key=lambda x: x["data"])
