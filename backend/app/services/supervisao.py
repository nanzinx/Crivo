"""Levantamento da monitoria para os supervisores: notas, falhas críticas, itens mais errados, evolução e ciência."""
from collections import defaultdict
from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Avaliacao, AvaliacaoCiencia, AvaliacaoItem, Call, ScriptItem, ScriptSecao
from . import equipes
from .avaliacoes import secao_aplica


def consulta(grupos: list[str] | None, data_inicio: date | None = None, data_fim: date | None = None,
             grupo: str | None = None, operador: str | None = None):
    """Avaliações do script finalizadas (com a ligação), no escopo do usuário."""
    stmt = (select(Avaliacao, Call).join(Call, Call.id == Avaliacao.call_id)
            .where(Avaliacao.status == "finalizada", Avaliacao.script_versao_id.is_not(None)))
    if grupos is not None:
        stmt = stmt.where(equipes.filtro(grupos))
    if data_inicio:
        stmt = stmt.where(Call.data_ligacao >= datetime.combine(data_inicio, time.min))
    if data_fim:
        stmt = stmt.where(Call.data_ligacao < datetime.combine(data_fim + timedelta(days=1), time.min))
    if grupo:
        stmt = stmt.where(Call.grupo_origem == grupo)
    if operador:
        stmt = stmt.where(Call.operador_nome == operador)
    return stmt


def ciencias(db: Session, ids: list[int]) -> dict[int, AvaliacaoCiencia]:
    if not ids:
        return {}
    return {c.avaliacao_id: c for c in db.scalars(select(AvaliacaoCiencia).where(AvaliacaoCiencia.avaliacao_id.in_(ids)))}


def _media(xs: list[float]) -> float | None:
    return round(sum(xs) / len(xs), 1) if xs else None


def resumo(db: Session, stmt) -> dict:
    rows = db.execute(stmt).all()
    ids = [a.id for a, _ in rows]
    cien = ciencias(db, ids)
    notas = [a.nota for a, _ in rows if a.nota is not None]

    ops: dict[str, dict] = {}
    semanas: dict[date, list] = defaultdict(list)
    for a, c in rows:
        nome = c.operador_nome or "Sem operador"
        o = ops.setdefault(nome, {"operador": nome, "grupo": c.grupo_origem, "avaliacoes": 0, "notas": [],
                                  "falhas_criticas": 0, "sem_ciencia": 0, "ultima": None})
        o["avaliacoes"] += 1
        if a.nota is not None:
            o["notas"].append(a.nota)
        o["falhas_criticas"] += int(bool(a.falha_critica))
        o["sem_ciencia"] += int(a.id not in cien)
        d = c.data_ligacao or a.finalizada_em
        if d and (o["ultima"] is None or d > o["ultima"]):
            o["ultima"] = d
        if d:
            semanas[d.date() - timedelta(days=d.weekday())].append(a)
    operadores = sorted(
        ({**{k: v for k, v in o.items() if k != "notas"}, "nota_media": _media(o["notas"]),
          "ultima": o["ultima"].isoformat() if o["ultima"] else None} for o in ops.values()),
        key=lambda o: (o["nota_media"] if o["nota_media"] is not None else 999, -o["avaliacoes"]))
    evolucao = [{"semana": s.isoformat(), "avaliacoes": len(av),
                 "nota_media": _media([a.nota for a in av if a.nota is not None]),
                 "falhas_criticas": sum(1 for a in av if a.falha_critica)} for s, av in sorted(semanas.items())]

    return {
        "avaliacoes": len(rows),
        "nota_media": _media(notas),
        "falhas_criticas": sum(1 for a, _ in rows if a.falha_critica),
        "falha_critica_pct": round(100 * sum(1 for a, _ in rows if a.falha_critica) / len(rows), 1) if rows else 0,
        "sem_ciencia": sum(1 for i in ids if i not in cien),
        "operadores": operadores,
        "evolucao": evolucao,
        "itens": itens_mais_errados(db, {a.id: a for a, _ in rows}),
    }


def itens_mais_errados(db: Session, avs: dict[int, Avaliacao], limite: int = 12) -> list[dict]:
    """Por trecho do script (agrupado pelo texto, para juntar versões): erros e divergências nas avaliações."""
    if not avs:
        return []
    rows = db.execute(
        select(AvaliacaoItem.avaliacao_id, AvaliacaoItem.estado, ScriptItem.texto, ScriptItem.critico,
               ScriptSecao.titulo, ScriptSecao.aplicabilidade)
        .join(ScriptItem, ScriptItem.id == AvaliacaoItem.item_id)
        .join(ScriptSecao, ScriptSecao.id == ScriptItem.secao_id)
        .where(AvaliacaoItem.avaliacao_id.in_(list(avs)), AvaliacaoItem.estado.is_not(None))
    ).all()
    por: dict[str, dict] = {}
    for aid, estado, texto, critico, secao, apl in rows:
        if not secao_aplica(apl, avs[aid].desfecho) or estado == "nao_se_aplica":
            continue
        it = por.setdefault(texto, {"texto": texto, "secao": secao, "critico": bool(critico), "avaliados": 0,
                                    "acertou": 0, "errou": 0, "divergencia": 0})
        it["avaliados"] += 1
        it[estado] += 1
    out = []
    for it in por.values():
        it["erro_pct"] = round(100 * it["errou"] / it["avaliados"], 1)
        it["divergencia_pct"] = round(100 * it["divergencia"] / it["avaliados"], 1)
        out.append(it)
    out.sort(key=lambda i: (i["errou"] + 0.5 * i["divergencia"]) / i["avaliados"], reverse=True)
    return [i for i in out if i["errou"] or i["divergencia"]][:limite]


def linha(a: Avaliacao, c: Call, ci: AvaliacaoCiencia | None) -> dict:
    iso = lambda d: d.isoformat() if d else None  # noqa: E731
    return {
        "id": a.id, "call_id": c.id, "id_ligacao": c.id_ligacao, "data_ligacao": iso(c.data_ligacao),
        "operador_nome": c.operador_nome, "grupo": c.grupo_origem, "tabulacao_operador": c.tabulacao_operador,
        "monitora_nome": a.monitora_nome, "finalizada_em": iso(a.finalizada_em), "nota": a.nota,
        "falha_critica": bool(a.falha_critica), "desfecho": a.desfecho, "categoria": a.categoria,
        "divergencia_tabulacao": bool(c.divergencia_tabulacao), "observacao": a.observacao,
        "feedback_fortes": a.feedback_fortes, "feedback_melhorar": a.feedback_melhorar,
        "ciencia": serializar_ciencia(ci),
    }


def serializar_ciencia(ci: AvaliacaoCiencia | None) -> dict | None:
    if ci is None:
        return None
    return {"por": ci.usuario_nome, "em": ci.em.isoformat(), "devolutiva": ci.devolutiva}
