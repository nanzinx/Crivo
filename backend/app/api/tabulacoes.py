"""Modelo de tabulação: listar, corrigir/confirmar, importar e exportar o significado de cada tabulação do Argus."""
import csv
import io
import unicodedata
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, model_validator
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Call, Tabulacao, agora
from ..services import pipeline, tabulacoes
from ..services.local_ingestor import _decode, _delim
from ..taxonomy import CATEGORIES, label_cat, label_sub

router = APIRouter(prefix="/api/v1/tabulacoes", tags=["tabulacoes"])


class RegraIn(BaseModel):
    tipo: Literal["resultado", "nao_tabulado", "ignorar"]
    categorias: list[str] = []
    subcategoria: str | None = None
    nao_ligar: bool = False

    @model_validator(mode="after")
    def _validar(self):
        invalidas = [c for c in self.categorias if c not in CATEGORIES or c == "INDETERMINADO"]
        if invalidas:
            raise ValueError(f"Categorias inválidas: {', '.join(invalidas)}")
        if self.tipo == "resultado" and not self.categorias:
            raise ValueError("Uma tabulação de resultado precisa de ao menos uma categoria.")
        if self.tipo != "resultado":
            self.categorias, self.subcategoria = [], None
        if self.subcategoria and not any(self.subcategoria in CATEGORIES[c]["subs"] for c in self.categorias):
            raise ValueError("A subcategoria precisa pertencer a uma das categorias escolhidas.")
        self.categorias = list(dict.fromkeys(self.categorias))
        return self


def _serializar(row: Tabulacao, stats: dict | None = None) -> dict:
    st = stats or {}
    lig, qual, div = st.get("ligacoes", 0), st.get("qualificadas", 0), st.get("divergencias", 0)
    return {
        "id": row.id,
        "nome": row.nome,
        "id_argus": row.id_argus,
        "tipo": row.tipo,
        "categorias": row.categorias or [],
        "subcategoria": row.subcategoria,
        "nao_ligar": bool(row.nao_ligar),
        "confirmada": bool(row.confirmada),
        "atualizado_em": row.atualizado_em.isoformat() if row.atualizado_em else None,
        "ligacoes": lig,
        "qualificadas": qual,
        "divergencias": div,
        "divergencias_altas": st.get("altas", 0),
        "taxa_divergencia": round(100 * div / qual, 1) if qual else 0,
    }


def _stats(db: Session) -> dict[int, dict]:
    avaliada = Call.status == "avaliada"
    rows = db.execute(
        select(Call.tabulacao_id, func.count(Call.id), func.sum(case((avaliada, 1), else_=0)),
               func.sum(case((Call.divergencia_tabulacao.is_(True), 1), else_=0)),
               func.sum(case((Call.divergencia_gravidade == "alta", 1), else_=0)))
        .where(Call.tabulacao_id.is_not(None)).group_by(Call.tabulacao_id)
    ).all()
    return {r[0]: {"ligacoes": r[1], "qualificadas": r[2] or 0, "divergencias": r[3] or 0, "altas": r[4] or 0}
            for r in rows}


@router.get("")
def listar(db: Session = Depends(get_db)):
    """Catálogo de tabulações com uso e divergência. Liga antes as ligações antigas ainda sem vínculo."""
    pipeline.vincular_pendentes(db)
    stats = _stats(db)
    itens = [_serializar(r, stats.get(r.id)) for r in db.scalars(select(Tabulacao))]
    itens.sort(key=lambda i: (i["confirmada"], -i["ligacoes"], i["nome"]))
    pendentes = [i for i in itens if not i["confirmada"] and i["ligacoes"]]
    return {
        "itens": itens,
        "resumo": {
            "total": len(itens),
            "confirmadas": sum(i["confirmada"] for i in itens),
            "pendentes": len(pendentes),
            "ligacoes_pendentes": sum(i["ligacoes"] for i in pendentes),
            "nao_ligar_registrado": any(i["nao_ligar"] for i in itens),
        },
        "opcoes": {
            "tipos": tabulacoes.TIPOS,
            "categorias": {k: {"label": v["label"], "subs": v["subs"]} for k, v in CATEGORIES.items()
                           if k != "INDETERMINADO"},
            "gravidades": pipeline.GRAVIDADES,
        },
    }


def _aplicar(row: Tabulacao, r: RegraIn) -> bool:
    """Grava a regra e confirma. Devolve True se o pedido de não ligar mudou (afeta outras tabulações)."""
    mudou_nao_ligar = bool(row.nao_ligar) != r.nao_ligar
    row.tipo, row.categorias, row.subcategoria, row.nao_ligar = r.tipo, r.categorias, r.subcategoria, r.nao_ligar
    row.confirmada, row.atualizado_em = True, agora()
    return mudou_nao_ligar


@router.put("/{tab_id}")
def editar(tab_id: int, regra: RegraIn, db: Session = Depends(get_db)):
    """Corrige/confirma o significado de uma tabulação e recalcula as ligações afetadas."""
    row = db.get(Tabulacao, tab_id)
    if not row:
        raise HTTPException(404, "Tabulação não encontrada")
    mudou_nao_ligar = _aplicar(row, regra)
    db.commit()
    total, mudaram = pipeline.recalcular(db, {tab_id}, incluir_nao_ligar=mudou_nao_ligar)
    return {"tabulacao": _serializar(row, _stats(db).get(tab_id)), "recalculadas": total, "mudaram": mudaram}


# --------------------------------------------------------------------------- planilha
COLUNAS = ["id", "id_argus", "tabulacao", "tipo", "categorias", "subcategoria", "nao_ligar", "confirmada", "ligacoes"]


@router.get("/exportar")
def exportar(db: Session = Depends(get_db)):
    """Modelo atual em CSV (';' + BOM). Serve de planilha para editar e importar de volta."""
    stats = _stats(db)
    out = io.StringIO()
    w = csv.writer(out, delimiter=";", lineterminator="\n")
    w.writerow(COLUNAS)
    for r in sorted(db.scalars(select(Tabulacao)), key=lambda r: r.nome.lower()):
        w.writerow([r.id, r.id_argus or "", r.nome, r.tipo, "|".join(r.categorias or []), r.subcategoria or "",
                    "sim" if r.nao_ligar else "não", "sim" if r.confirmada else "não",
                    stats.get(r.id, {}).get("ligacoes", 0)])
    return Response(out.getvalue().encode("utf-8-sig"), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="crivo_modelo_tabulacao.csv"'})


def _nk(s: str | None) -> str:
    s = unicodedata.normalize("NFD", (s or "").strip().lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def _indices():
    cats, subs = {}, {}
    for code, v in CATEGORIES.items():
        cats[_nk(code)] = cats[_nk(v["label"])] = code
        for sc, sl in v["subs"].items():
            subs[_nk(sc)] = subs[_nk(sl)] = sc
    tipos = {_nk(k): k for k in tabulacoes.TIPOS} | {_nk(v): k for k, v in tabulacoes.TIPOS.items()}
    tipos |= {"nao tabulado": "nao_tabulado", "ignorada": "ignorar"}
    return cats, subs, tipos


@router.post("/importar")
async def importar(arquivo: UploadFile = File(...), db: Session = Depends(get_db)):
    """Importa o modelo de uma planilha CSV (colunas: tabulacao; tipo; categorias; subcategoria; nao_ligar;
    opcionalmente id_argus). Categorias e subcategorias podem vir pelo código ou pelo nome, várias separadas
    por '|'. Cada linha válida fica confirmada; linhas com erro são listadas e não alteram nada."""
    texto = _decode(await arquivo.read())
    leitor = csv.DictReader(io.StringIO(texto), delimiter=_delim(texto))
    leitor.fieldnames = [_nk(h).replace(" ", "_") for h in leitor.fieldnames or []]
    if "tabulacao" not in leitor.fieldnames:
        raise HTTPException(400, "A planilha precisa de uma coluna 'tabulacao'.")
    cats, subs, tipos = _indices()
    importadas, erros, afetadas, mudou_nao_ligar = 0, [], set(), False
    for n, linha in enumerate(leitor, start=2):
        nome = (linha.get("tabulacao") or "").strip()
        if not nome:
            continue
        try:
            tipo = tipos.get(_nk(linha.get("tipo")) or "resultado")
            if not tipo:
                raise ValueError(f"tipo desconhecido '{linha.get('tipo')}'")
            nomes_cat = [c for c in (linha.get("categorias") or linha.get("categoria") or "").replace(",", "|").split("|")
                         if c.strip()]
            desconhecidas = [c.strip() for c in nomes_cat if _nk(c) not in cats]
            if desconhecidas:
                raise ValueError(f"categoria desconhecida: {', '.join(desconhecidas)}")
            sub_txt = (linha.get("subcategoria") or "").strip()
            if sub_txt and _nk(sub_txt) not in subs:
                raise ValueError(f"subcategoria desconhecida: {sub_txt}")
            regra = RegraIn(tipo=tipo, categorias=[cats[_nk(c)] for c in nomes_cat],
                            subcategoria=subs[_nk(sub_txt)] if sub_txt else None,
                            nao_ligar=_nk(linha.get("nao_ligar")) in ("sim", "s", "x", "1", "true", "verdadeiro"))
            id_argus = (linha.get("id_argus") or "").strip()
            row = tabulacoes.obter_ou_criar(db, nome, int(id_argus) if id_argus.isdigit() else None)
        except ValueError as e:  # inclui a validação da RegraIn
            msg = str(e).split("\n")[-1] if "validation error" in str(e) else str(e)
            erros.append(f"Linha {n} ({nome}): {msg}")
            continue
        mudou_nao_ligar |= _aplicar(row, regra)
        afetadas.add(row.id)
        importadas += 1
    db.commit()
    total, mudaram = pipeline.recalcular(db, afetadas, incluir_nao_ligar=mudou_nao_ligar) if afetadas else (0, 0)
    return {"importadas": importadas, "erros": erros, "recalculadas": total, "mudaram": mudaram}


@router.get("/rotulos")
def rotulos():
    """Rótulos das categorias/subcategorias (para telas)."""
    return {c: {"label": label_cat(c), "subs": {s: label_sub(c, s) for s in v["subs"]}} for c, v in CATEGORIES.items()}
