"""Painel integrado: página do operador (ligações + monitoria + ponto) e o resumo da Visão geral."""
from datetime import datetime, time, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Avaliacao, AvaliacaoCiencia, Call, PontoImportacao, PontoJornada, agora
from ..services import avaliacoes, equipes, ponto, supervisao
from .auth import escopo_equipe

router = APIRouter(prefix="/api/v1", tags=["operadores"])


def _equipe(db: Session, nome: str) -> str | None:
    return ponto.equipe_do_operador(db, nome) or db.scalar(
        select(Call.grupo_origem).where(Call.operador_nome == nome, Call.grupo_origem.is_not(None))
        .order_by(Call.data_ligacao.desc()).limit(1))


@router.get("/operadores/{nome}/resumo")
def resumo_operador(nome: str, dias: int = 30, db: Session = Depends(get_db), grupos=Depends(escopo_equipe)):
    equipe = _equipe(db, nome)
    tem_dados = db.scalar(select(func.count(Call.id)).where(Call.operador_nome == nome)) or \
        db.scalar(select(func.count(PontoJornada.id)).where(PontoJornada.operador == nome))
    if not tem_dados or (grupos is not None and equipe not in grupos):
        raise HTTPException(404, "Operador não encontrado")
    ini = datetime.combine(agora().date() - timedelta(days=max(1, dias) - 1), time.min)

    avaliada = Call.status == avaliacoes.AVALIADA
    tot, aval, div, altas = db.execute(select(
        func.count(Call.id), func.sum(case((avaliada, 1), else_=0)),
        func.sum(case((avaliada & Call.divergencia_tabulacao.is_(True), 1), else_=0)),
        func.sum(case((avaliada & (Call.divergencia_gravidade == "alta"), 1), else_=0)))
        .where(Call.operador_nome == nome, Call.data_ligacao >= ini)).one()
    aval, div = aval or 0, div or 0

    stmt = supervisao.consulta(None, ini.date(), None, None, nome)
    rows = db.execute(stmt.order_by(Call.data_ligacao.desc())).all()
    cien = supervisao.ciencias(db, [a.id for a, _ in rows])
    notas = [a.nota for a, _ in rows if a.nota is not None]

    # ponto: últimos dias importados em que o operador aparece
    dias_ponto = db.scalars(select(PontoJornada.data).distinct().where(PontoJornada.operador == nome)
                            .order_by(PontoJornada.data.desc()).limit(10)).all()
    com_pausas = {d for (d,) in db.execute(select(PontoImportacao.data_ref).where(PontoImportacao.tipo == "pausas"))}
    historico = []
    for d in dias_ponto:
        linha = next((v for v in ponto.relatorio(db, d, d in com_pausas) if v.operador.casefold() == nome.casefold()), None)
        if linha:
            historico.append({"data": d.isoformat(), "completo": d in com_pausas, **linha.to_dict()})

    return {
        "operador": nome, "equipe": equipe, "dias": dias,
        "ligacoes": {"total": tot or 0, "avaliadas": aval, "divergencias": div, "altas": altas or 0,
                     "taxa_divergencia": round(100 * div / aval, 1) if aval else 0},
        "monitoria": {
            "avaliacoes": len(rows), "nota_media": round(sum(notas) / len(notas), 1) if notas else None,
            "falhas_criticas": sum(1 for a, _ in rows if a.falha_critica),
            "sem_ciencia": sum(1 for a, _ in rows if a.id not in cien),
            "notas": [{"call_id": c.id, "data": c.data_ligacao.isoformat() if c.data_ligacao else None, "nota": a.nota,
                       "falha_critica": bool(a.falha_critica)} for a, c in reversed(rows[:20])],
            "itens": supervisao.itens_mais_errados(db, {a.id: a for a, _ in rows}, limite=5),
            "avaliacoes_recentes": [supervisao.linha(a, c, cien.get(a.id)) for a, c in rows[:8]],
        },
        "ponto": {"dias": historico, "atrasos": sum(1 for h in historico if h["atraso_min"]),
                  "almoco_acima_1h": sum(1 for h in historico if (h["almoco_seg"] or 0) > 3600)},
    }


@router.get("/painel")
def painel(db: Session = Depends(get_db), grupos=Depends(escopo_equipe)):
    """Resumo da monitoria e do ponto para a Visão geral (supervisor: só as equipes dele)."""
    t = agora()
    hoje = datetime.combine(t.date(), time.min)
    filtro = equipes.filtro(grupos) if grupos is not None else None

    def com_escopo(stmt):
        return stmt.where(filtro) if filtro is not None else stmt

    base = (select(Avaliacao).join(Call, Call.id == Avaliacao.call_id)
            .where(Avaliacao.status == "finalizada", Avaliacao.script_versao_id.is_not(None)))
    sete = db.scalars(com_escopo(base.where(Avaliacao.finalizada_em >= hoje - timedelta(days=6)))).all()
    notas = [a.nota for a in sete if a.nota is not None]
    monitoria = {
        "avaliadas_hoje": db.scalar(com_escopo(select(func.count(Avaliacao.id)).join(Call, Call.id == Avaliacao.call_id)
                                               .where(Avaliacao.status.in_(("finalizada", "nao_avaliavel")),
                                                      Avaliacao.finalizada_em >= hoje))) or 0,
        "aguardando": db.scalar(com_escopo(select(func.count(Call.id))
                                           .where(Call.status == avaliacoes.PENDENTE_AVALIACAO))) or 0,
        "nota_media_7d": round(sum(notas) / len(notas), 1) if notas else None,
        "falhas_criticas_7d": sum(1 for a in sete if a.falha_critica),
        "sem_ciencia": db.scalar(com_escopo(select(func.count(Avaliacao.id)).join(Call, Call.id == Avaliacao.call_id)
                                            .where(Avaliacao.status == "finalizada", Avaliacao.script_versao_id.is_not(None),
                                                   Avaliacao.id.not_in(select(AvaliacaoCiencia.avaliacao_id))))) or 0,
    }
    ultimo = db.scalar(select(func.max(PontoJornada.data)))  # o último dia importado
    ponto_resumo = None
    if ultimo:
        completo = bool(db.scalar(select(func.count(PontoImportacao.id)).where(
            PontoImportacao.tipo == "pausas", PontoImportacao.data_ref == ultimo)))
        linhas = ponto.relatorio(db, ultimo, completo, grupos)
        ponto_resumo = {"data": ultimo.isoformat(), **ponto.resumo(linhas, completo), "completo": completo,
                        "atrasados": [{"operador": v.operador, "minutos": v.atraso_min} for v in linhas if v.atraso_min][:6]}
    return {"monitoria": monitoria, "ponto": ponto_resumo}
