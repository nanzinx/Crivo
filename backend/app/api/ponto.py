"""Controle de ponto (substitui a planilha "Controle de Ponto - Argus"): importação, relatórios e configuração."""
import csv
import io
from datetime import date

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Parametro, PontoGrupo, PontoImportacao, PontoJornada, PontoPausaConfig, agora
from ..services import ponto
from .auth import escopo_equipe, exigir_papel

router = APIRouter(prefix="/api/v1/ponto", tags=["ponto"])
quem_importa = exigir_papel("monitora", "admin", mensagem="Só a monitoria e os administradores importam o ponto.")


def _hhmm(seg: int | None, com_seg: bool = False) -> str:
    if seg is None:
        return ""
    h, r = divmod(int(seg), 3600)
    return f"{h:02d}:{r // 60:02d}" + (f":{r % 60:02d}" if com_seg else "")


@router.post("/importar")
async def importar(request: Request, arquivos: list[UploadFile] = File(...), db: Session = Depends(get_db),
                   _u=Depends(quem_importa)):
    """Recebe os CSVs do Argus (entrada/saída e pausas, de um ou mais dias) e reconhece cada um sozinho."""
    u = getattr(request.state, "usuario", None)
    out = []
    for arq in arquivos:
        dados = await arq.read()
        if len(dados) > 20 * 1024 * 1024:
            out.append({"arquivo": arq.filename, "erro": "arquivo maior que 20 MB"})
            continue
        r = ponto.importar(db, arq.filename or "arquivo.csv", dados, u.nome if u else "Acesso local")
        out.append({"arquivo": r.arquivo, "tipo": r.tipo, "data": r.data.isoformat() if r.data else None,
                    "linhas": r.linhas, "erro": r.erro, "substituiu": r.substituiu})
    db.commit()
    return {"arquivos": out}


@router.get("/importacoes")
def importacoes(db: Session = Depends(get_db)):
    rows = db.scalars(select(PontoImportacao).order_by(PontoImportacao.importado_em.desc()).limit(30)).all()
    return [{"id": i.id, "tipo": i.tipo, "data": i.data_ref.isoformat(), "arquivo": i.arquivo, "linhas": i.linhas,
             "importado_em": i.importado_em.isoformat(), "importado_por": i.importado_por} for i in rows]


@router.get("/datas")
def datas(db: Session = Depends(get_db)):
    """Dias com ponto importado, mais recentes primeiro, e se têm as pausas (relatório completo)."""
    pausas = {d for (d,) in db.execute(select(PontoImportacao.data_ref).where(PontoImportacao.tipo == "pausas"))}
    dias = db.scalars(select(PontoJornada.data).distinct().order_by(PontoJornada.data.desc())).all()
    return [{"data": d.isoformat(), "tem_pausas": d in pausas} for d in dias]


def _relatorio(db, data, modo, grupo, grupos):
    completo = modo != "entrada"
    linhas = ponto.relatorio(db, data, completo, grupos)
    if grupo:
        linhas = [v for v in linhas if v.grupo == grupo]
    return linhas, completo


@router.get("/relatorio")
def relatorio(data: date, modo: str = "completo", grupo: str | None = None, db: Session = Depends(get_db),
              grupos=Depends(escopo_equipe)):
    """modo=completo (dia fechado: entrada, saída, almoço, TMP, QTP, atraso) ou entrada (dia em andamento)."""
    linhas, completo = _relatorio(db, data, modo, grupo, grupos)
    return {"data": data.isoformat(), "modo": "completo" if completo else "entrada",
            "resumo": ponto.resumo(linhas, completo), "linhas": [v.to_dict() for v in linhas]}


@router.get("/exportar")
def exportar(data: date, modo: str = "completo", grupo: str | None = None, db: Session = Depends(get_db),
             grupos=Depends(escopo_equipe)):
    linhas, completo = _relatorio(db, data, modo, grupo, grupos)
    out = io.StringIO()
    w = csv.writer(out, delimiter=";")
    w.writerow(["Colaborador", "Equipe", "Entrada", "Saída", "Tempo", "Almoço entrada", "Almoço saída", "Almoço tempo",
                "TMP", "QTP", "Observação"])
    for v in linhas:
        d = v.to_dict()
        w.writerow([v.operador, v.grupo or "", _hhmm(v.entrada), _hhmm(v.saida), _hhmm(v.jornada_seg),
                    v.almoco_inicio.strftime("%d/%m/%Y %H:%M") if v.almoco_inicio else "",
                    v.almoco_fim.strftime("%d/%m/%Y %H:%M") if v.almoco_fim else "", _hhmm(v.almoco_seg, True),
                    _hhmm(v.tmp_seg, True), v.qtp if v.qtp is not None else "", d["observacao"] or ""])
    nome = f"ponto_{data.isoformat()}{'' if completo else '_entradas'}.csv"
    return StreamingResponse(iter(["﻿" + out.getvalue()]), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": f'attachment; filename="{nome}"'})


# --------------------------------------------------------------------------- configuração
@router.get("/config")
def ler_config(db: Session = Depends(get_db)):
    uso = dict(db.execute(select(PontoJornada.grupo, func.count(func.distinct(PontoJornada.operador)))
                          .group_by(PontoJornada.grupo)).all())
    return {
        "grupos": [{"grupo": g.grupo, "incluir": g.incluir, "entrada_prevista": g.entrada_prevista or "",
                    "tolerancia_min": g.tolerancia_min, "operadores": uso.get(g.grupo, 0)}
                   for g in db.scalars(select(PontoGrupo).order_by(PontoGrupo.grupo))],
        "pausas": [{"descricao": p.descricao, "conta": p.conta}
                   for p in db.scalars(select(PontoPausaConfig).order_by(func.lower(PontoPausaConfig.descricao)))],
        "almoco": ponto.parametro(db, "ponto_almoco"),
        "ignorar": ponto.parametro(db, "ponto_ignorar"),
    }


class GrupoIn(BaseModel):
    grupo: str
    incluir: bool
    entrada_prevista: str = ""
    tolerancia_min: int = Field(10, ge=0, le=240)


class ConfigIn(BaseModel):
    grupos: list[GrupoIn] | None = None
    pausas: list[dict] | None = None
    almoco: str | None = None
    ignorar: str | None = None


@router.put("/config")
def salvar_config(dados: ConfigIn, db: Session = Depends(get_db), _u=Depends(quem_importa)):
    for g in dados.grupos or []:
        for txt in g.entrada_prevista.replace(",", ";").split(";"):
            if txt.strip() and ponto.hora_seg(txt) is None:
                raise HTTPException(422, f"Horário inválido em {g.grupo}: {txt!r} (use 10:00 ou 08:30;14:00)")
        row = db.get(PontoGrupo, g.grupo) or PontoGrupo(grupo=g.grupo)
        row.incluir, row.entrada_prevista, row.tolerancia_min = g.incluir, g.entrada_prevista.strip(), g.tolerancia_min
        db.add(row)
    for p in dados.pausas or []:
        row = db.get(PontoPausaConfig, p["descricao"]) or PontoPausaConfig(descricao=p["descricao"])
        row.conta = bool(p.get("conta"))
        db.add(row)
    for k, v in (("ponto_almoco", dados.almoco), ("ponto_ignorar", dados.ignorar)):
        if v is not None:
            row = db.get(Parametro, k) or Parametro(chave=k)
            row.valor, row.atualizado_em = v.strip(), agora()
            db.add(row)
    db.commit()
    return ler_config(db)
