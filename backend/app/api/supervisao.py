"""Visão dos supervisores: levantamento da monitoria da própria equipe, ciência e devolutiva; equipes (admin)."""
import csv
import io
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Avaliacao, AvaliacaoCiencia, Call, Usuario, agora
from ..services import equipes, supervisao
from .auth import escopo_equipe, exigir_admin, exigir_papel

router = APIRouter(prefix="/api/v1", tags=["supervisao"])
quem_da_ciencia = exigir_papel("supervisor", "admin", mensagem="Só supervisores registram a ciência da avaliação.")


@router.get("/supervisao/resumo")
def resumo(data_inicio: date | None = None, data_fim: date | None = None, grupo: str | None = None,
           operador: str | None = None, db: Session = Depends(get_db), grupos=Depends(escopo_equipe)):
    r = supervisao.resumo(db, supervisao.consulta(grupos, data_inicio, data_fim, grupo, operador))
    r["escopo"] = {"restrito": grupos is not None, "grupos": grupos}
    return r


@router.get("/supervisao/avaliacoes")
def lista(data_inicio: date | None = None, data_fim: date | None = None, grupo: str | None = None,
          operador: str | None = None, ciencia: str | None = None, falha_critica: bool | None = None,
          page: int = 1, page_size: int = 30, db: Session = Depends(get_db), grupos=Depends(escopo_equipe)):
    stmt = supervisao.consulta(grupos, data_inicio, data_fim, grupo, operador)
    com_ciencia = select(AvaliacaoCiencia.avaliacao_id)
    if ciencia == "pendente":
        stmt = stmt.where(Avaliacao.id.not_in(com_ciencia))
    elif ciencia == "feita":
        stmt = stmt.where(Avaliacao.id.in_(com_ciencia))
    if falha_critica is not None:
        stmt = stmt.where(Avaliacao.falha_critica.is_(falha_critica))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    page_size = max(1, min(page_size, 100))
    rows = db.execute(stmt.order_by(Call.data_ligacao.desc().nullslast(), Avaliacao.id.desc())
                      .offset((max(page, 1) - 1) * page_size).limit(page_size)).all()
    cien = supervisao.ciencias(db, [a.id for a, _ in rows])
    return {"total": total, "page": page, "page_size": page_size,
            "itens": [supervisao.linha(a, c, cien.get(a.id)) for a, c in rows]}


@router.get("/supervisao/exportar")
def exportar(data_inicio: date | None = None, data_fim: date | None = None, grupo: str | None = None,
             operador: str | None = None, db: Session = Depends(get_db), grupos=Depends(escopo_equipe)):
    """CSV das avaliações (';' + BOM, abre direto no Excel)."""
    rows = db.execute(supervisao.consulta(grupos, data_inicio, data_fim, grupo, operador)
                      .order_by(Call.data_ligacao.desc()).limit(50000)).all()
    cien = supervisao.ciencias(db, [a.id for a, _ in rows])
    out = io.StringIO()
    w = csv.writer(out, delimiter=";")
    w.writerow(["ID Ligação", "Data/Hora", "Operador", "Equipe", "Tabulação", "Monitora", "Nota", "Falha crítica",
                "Desfecho", "Resultado", "Observação", "Pontos fortes", "A melhorar", "Ciência por", "Ciência em",
                "Devolutiva"])
    for a, c in rows:
        ci = cien.get(a.id)
        w.writerow([c.id_ligacao or c.id, c.data_ligacao.strftime("%d/%m/%Y %H:%M") if c.data_ligacao else "",
                    c.operador_nome or "", c.grupo_origem or "", c.tabulacao_operador or "", a.monitora_nome or "",
                    f"{a.nota:.1f}".replace(".", ",") if a.nota is not None else "", "Sim" if a.falha_critica else "Não",
                    a.desfecho or "", a.categoria or "", a.observacao or "", a.feedback_fortes or "",
                    a.feedback_melhorar or "", ci.usuario_nome if ci else "",
                    ci.em.strftime("%d/%m/%Y %H:%M") if ci else "", (ci.devolutiva or "") if ci else ""])
    return StreamingResponse(iter(["﻿" + out.getvalue()]), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": 'attachment; filename="crivo_avaliacoes.csv"'})


class CienciaIn(BaseModel):
    devolutiva: str | None = None


@router.post("/avaliacoes/{aid}/ciencia")
def dar_ciencia(aid: int, dados: CienciaIn, request: Request, db: Session = Depends(get_db),
                grupos=Depends(escopo_equipe), _u=Depends(quem_da_ciencia)):
    """O supervisor registra que viu a avaliação e a devolutiva que deu ao operador (pode atualizar depois)."""
    a = db.get(Avaliacao, aid)
    c = db.get(Call, a.call_id) if a else None
    if not a or not c or not equipes.no_escopo(c, grupos):
        raise HTTPException(404, "Avaliação não encontrada")
    if a.status != "finalizada":
        raise HTTPException(409, "Só avaliações finalizadas recebem ciência.")
    u = getattr(request.state, "usuario", None)
    ci = db.scalars(select(AvaliacaoCiencia).where(AvaliacaoCiencia.avaliacao_id == a.id)).first()
    ci = ci or AvaliacaoCiencia(avaliacao_id=a.id)
    ci.usuario_id, ci.usuario_nome = (u.id if u else None), ((u.nome if u else None) or "Acesso local")[:80]
    ci.em, ci.devolutiva = agora(), (dados.devolutiva or "").strip()[:2000] or None
    db.add(ci)
    db.commit()
    return supervisao.serializar_ciencia(ci)


# --------------------------------------------------------------------------- equipes dos supervisores (admin)
@router.get("/equipes")
def listar_equipes(db: Session = Depends(get_db), _u=Depends(exigir_admin)):
    """Equipes (grupos do Argus) conhecidas e quais supervisores acompanham cada uma."""
    grupos = db.execute(select(Call.grupo_origem, func.count(Call.id)).where(Call.grupo_origem.is_not(None))
                        .group_by(Call.grupo_origem).order_by(Call.grupo_origem)).all()
    sups = db.scalars(select(Usuario).where(Usuario.papel == "supervisor").order_by(Usuario.nome)).all()
    return {"grupos": [{"nome": g, "ligacoes": n} for g, n in grupos],
            "supervisores": [{"id": s.id, "nome": s.nome, "ativo": s.ativo, "grupos": equipes.grupos_do(db, s.id)}
                             for s in sups]}


class GruposIn(BaseModel):
    grupos: list[str]


@router.put("/usuarios/{uid}/grupos")
def definir_grupos(uid: int, dados: GruposIn, db: Session = Depends(get_db), _u=Depends(exigir_admin)):
    u = db.get(Usuario, uid)
    if not u:
        raise HTTPException(404, "Usuário não encontrado")
    if u.papel != "supervisor":
        raise HTTPException(409, "Só supervisores têm equipes vinculadas.")
    grupos = equipes.definir(db, uid, dados.grupos)
    db.commit()
    return {"id": uid, "grupos": grupos}
