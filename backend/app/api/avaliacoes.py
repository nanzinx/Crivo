"""Avaliação das ligações pela monitoria: script de vendas versionado, fila, rascunho com trava, finalização."""
from datetime import date, datetime, time

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Avaliacao, Call, Parametro, ScriptVersao, agora
from ..services import avaliacoes, equipes, script, supervisao
from .auth import escopo_equipe, exigir_papel

router = APIRouter(prefix="/api/v1", tags=["avaliacoes"])
monitoria = exigir_papel("monitora", "admin", mensagem="Só a monitoria de qualidade avalia ligações.")
so_admin = exigir_papel("admin", mensagem="Só administradores editam o script e os parâmetros.")

PARAMETROS = {"meta_diaria": ("Meta diária de avaliações por monitora", "30")}


def _usuario(request: Request):
    return getattr(request.state, "usuario", None)


def _erro(e: Exception):
    if isinstance(e, avaliacoes.Invalida):
        raise HTTPException(422, {"mensagem": "A avaliação ainda não pode ser concluída.", "problemas": e.problemas})
    raise HTTPException(409, str(e))


def _avaliacao(db: Session, aid: int, grupos: list[str] | None = None) -> Avaliacao:
    a = db.get(Avaliacao, aid)
    c = db.get(Call, a.call_id) if a else None
    if not a or not c or not equipes.no_escopo(c, grupos):
        raise HTTPException(404, "Avaliação não encontrada")
    return a


# --------------------------------------------------------------------------- script
@router.get("/scripts/ativo")
def script_ativo(db: Session = Depends(get_db)):
    v = script.ativo(db)
    if not v:
        raise HTTPException(404, "Nenhum script ativo")
    return script.serializar(db, v)


@router.get("/scripts/versoes")
def script_versoes(db: Session = Depends(get_db)):
    vs = db.scalars(select(ScriptVersao).order_by(ScriptVersao.numero.desc())).all()
    return [{"id": v.id, "nome": v.nome, "numero": v.numero, "status": v.status, "criado_por": v.criado_por,
             "criado_em": v.criado_em.isoformat() if v.criado_em else None,
             "publicada_em": v.publicada_em.isoformat() if v.publicada_em else None,
             "avaliacoes": script.em_uso(db, v.id)} for v in vs]


@router.get("/scripts/versoes/{vid}")
def script_versao(vid: int, db: Session = Depends(get_db)):
    v = db.get(ScriptVersao, vid)
    if not v:
        raise HTTPException(404, "Versão não encontrada")
    return script.serializar(db, v)


@router.post("/scripts/versoes")
def script_novo_rascunho(request: Request, db: Session = Depends(get_db), _u=Depends(so_admin)):
    """Nova versão em rascunho, copiando a ativa. Se já existe um rascunho, devolve ele."""
    rasc = db.scalars(select(ScriptVersao).where(ScriptVersao.status == "rascunho")).first()
    if not rasc:
        u = _usuario(request)
        rasc = script.novo_rascunho(db, script.ativo(db), u.nome if u else "Acesso local")
        db.commit()
    return script.serializar(db, rasc)


class ItemIn(BaseModel):
    texto: str = Field(min_length=1)
    orientacao: str | None = None
    peso: float = Field(1.0, gt=0, le=100)
    critico: bool = False


class SecaoIn(BaseModel):
    titulo: str = Field(min_length=1)
    aplicabilidade: str = "sempre"
    orientacao: str | None = None
    itens: list[ItemIn] = []

    @field_validator("aplicabilidade")
    @classmethod
    def _apl(cls, v):
        if v not in script.APLICABILIDADES:
            raise ValueError("Aplicabilidade deve ser sempre, venda ou recusa.")
        return v


class ScriptIn(BaseModel):
    nome: str = Field(min_length=1)
    valor_divergencia: float = Field(0.5, ge=0, le=1)
    secoes: list[SecaoIn] = Field(min_length=1)


@router.put("/scripts/versoes/{vid}")
def script_salvar(vid: int, dados: ScriptIn, db: Session = Depends(get_db), _u=Depends(so_admin)):
    v = db.get(ScriptVersao, vid)
    if not v:
        raise HTTPException(404, "Versão não encontrada")
    if v.status != "rascunho" or script.em_uso(db, v.id):
        raise HTTPException(409, "Só um rascunho ainda não usado em avaliações pode ser editado. Crie uma nova versão.")
    script.substituir_estrutura(db, v, dados.nome, dados.valor_divergencia, [s.model_dump() for s in dados.secoes])
    db.commit()
    return script.serializar(db, v)


@router.post("/scripts/versoes/{vid}/publicar")
def script_publicar(vid: int, db: Session = Depends(get_db), _u=Depends(so_admin)):
    v = db.get(ScriptVersao, vid)
    if not v:
        raise HTTPException(404, "Versão não encontrada")
    if v.status != "rascunho":
        raise HTTPException(409, "Só um rascunho pode ser publicado.")
    if not any(itens for _, itens in script.secoes_e_itens(db, v.id)):
        raise HTTPException(422, "O script precisa de pelo menos um item.")
    script.publicar(db, v)
    db.commit()
    return script.serializar(db, v)


@router.delete("/scripts/versoes/{vid}")
def script_descartar(vid: int, db: Session = Depends(get_db), _u=Depends(so_admin)):
    v = db.get(ScriptVersao, vid)
    if not v or v.status != "rascunho" or script.em_uso(db, v.id):
        raise HTTPException(409, "Só um rascunho não usado pode ser descartado.")
    script.substituir_estrutura(db, v, v.nome, v.valor_divergencia, [])
    db.delete(v)
    db.commit()
    return {"ok": True}


# --------------------------------------------------------------------------- parâmetros
def parametro(db: Session, chave: str) -> str:
    p = db.get(Parametro, chave)
    return p.valor if p else PARAMETROS[chave][1]


@router.get("/parametros")
def ler_parametros(db: Session = Depends(get_db)):
    return {k: {"descricao": d, "valor": parametro(db, k)} for k, (d, _) in PARAMETROS.items()}


@router.put("/parametros")
def salvar_parametros(dados: dict[str, str], db: Session = Depends(get_db), _u=Depends(so_admin)):
    for k, v in dados.items():
        if k not in PARAMETROS:
            raise HTTPException(422, f"Parâmetro desconhecido: {k}")
        if k == "meta_diaria" and not str(v).isdigit():
            raise HTTPException(422, "A meta diária deve ser um número inteiro.")
        p = db.get(Parametro, k) or Parametro(chave=k)
        p.valor, p.atualizado_em = str(v), agora()
        db.add(p)
    db.commit()
    return ler_parametros(db)


# --------------------------------------------------------------------------- fila e avaliação
@router.get("/avaliacoes/fila")
def fila(request: Request, operador: str | None = None, data_inicio: date | None = None, data_fim: date | None = None,
         page: int = 1, page_size: int = 30, db: Session = Depends(get_db), grupos=Depends(escopo_equipe)):
    """Ligações com gravação esperando a monitoria (e rascunhos em andamento), mais antigas primeiro."""
    stmt = select(Call).where(Call.status.in_((avaliacoes.PENDENTE_AVALIACAO, avaliacoes.EM_AVALIACAO)))
    if grupos is not None:
        stmt = stmt.where(equipes.filtro(grupos))
    if operador:
        stmt = stmt.where(Call.operador_nome == operador)
    if data_inicio:
        stmt = stmt.where(Call.data_ligacao >= datetime.combine(data_inicio, time.min))
    if data_fim:
        stmt = stmt.where(Call.data_ligacao <= datetime.combine(data_fim, time.max))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    page_size = max(1, min(page_size, 100))
    calls = db.scalars(stmt.order_by(Call.data_ligacao.asc().nullslast(), Call.id)
                       .offset((max(page, 1) - 1) * page_size).limit(page_size)).all()
    avs = {a.id: a for a in db.scalars(select(Avaliacao).where(
        Avaliacao.id.in_([c.avaliacao_id for c in calls if c.avaliacao_id] or [-1])))}
    u = _usuario(request)
    hoje = datetime.combine(agora().date(), time.min)
    feitas = select(func.count(Avaliacao.id)).where(Avaliacao.finalizada_em >= hoje,
                                                    Avaliacao.status.in_(("finalizada", "nao_avaliavel")))
    if u:
        feitas = feitas.where(Avaliacao.monitora_id == u.id)
    itens = []
    for c in calls:
        a = avs.get(c.avaliacao_id)
        itens.append({
            "id": c.id, "id_ligacao": c.id_ligacao, "data_ligacao": c.data_ligacao.isoformat() if c.data_ligacao else None,
            "duracao_segundos": c.duracao_segundos, "operador_nome": c.operador_nome,
            "tabulacao_operador": c.tabulacao_operador, "grupo": c.grupo_origem, "status": c.status,
            "tem_audio": bool(c.caminho_audio),
            "rascunho": {"monitora": a.monitora_nome, "trava": a.trava_nome if avaliacoes.trava_ativa(a) else None,
                         "minha": avaliacoes.trava_ativa(a) and avaliacoes.e_minha(a, u)} if a else None,
        })
    return {"total": total, "page": page, "page_size": page_size, "itens": itens,
            "meta": {"diaria": int(parametro(db, "meta_diaria")), "feitas_hoje": db.scalar(feitas) or 0}}


@router.post("/calls/{call_id}/avaliacao")
def iniciar(call_id: int, request: Request, db: Session = Depends(get_db), _u=Depends(monitoria)):
    """Abre (ou retoma) a avaliação do script da ligação e trava para a monitora."""
    c = db.get(Call, call_id)
    if not c:
        raise HTTPException(404, "Ligação não encontrada")
    try:
        a = avaliacoes.iniciar(db, c, _usuario(request))
    except avaliacoes.Conflito as e:
        _erro(e)
    db.commit()
    return avaliacoes.serializar_completa(db, a, _usuario(request))


@router.get("/avaliacoes/{aid}")
def ler(aid: int, request: Request, db: Session = Depends(get_db), grupos=Depends(escopo_equipe)):
    a = _avaliacao(db, aid, grupos)
    d = avaliacoes.serializar_completa(db, a, _usuario(request))
    d["ciencia"] = supervisao.serializar_ciencia(supervisao.ciencias(db, [a.id]).get(a.id))
    return d


class ItemAvIn(BaseModel):
    item_id: int
    estado: str | None = None
    comentario: str | None = None

    @field_validator("estado")
    @classmethod
    def _est(cls, v):
        if v is not None and v not in avaliacoes.ESTADOS:
            raise ValueError("Estado deve ser acertou, errou, divergencia ou nao_se_aplica.")
        return v


class MarcaIn(BaseModel):
    item_id: int | None = None
    segundos: float = Field(ge=0)
    tipo: str = "nota"
    texto: str | None = None

    @field_validator("tipo")
    @classmethod
    def _tipo(cls, v):
        if v not in avaliacoes.TIPOS_MARCA:
            raise ValueError("Tipo deve ser acertou, errou, divergencia ou nota.")
        return v


class RascunhoIn(BaseModel):
    desfecho: str | None = None
    categoria: str | None = None
    subcategoria: str | None = None
    pediu_nao_ligar: bool | None = None
    observacao: str | None = None
    feedback_fortes: str | None = None
    feedback_melhorar: str | None = None
    itens: list[ItemAvIn] | None = None
    marcas: list[MarcaIn] | None = None

    @field_validator("desfecho")
    @classmethod
    def _desf(cls, v):
        if v is not None and v not in avaliacoes.DESFECHOS:
            raise ValueError("Desfecho deve ser venda, recusa, outro ou sem_conversa.")
        return v


@router.put("/avaliacoes/{aid}")
def salvar(aid: int, dados: RascunhoIn, request: Request, db: Session = Depends(get_db), _u=Depends(monitoria)):
    """Autosave do rascunho (renova a trava). Só os campos enviados mudam."""
    a = _avaliacao(db, aid)
    corpo = dados.model_dump(exclude_unset=True)
    try:
        avaliacoes.salvar(db, a, _usuario(request), corpo)
    except avaliacoes.Conflito as e:
        db.rollback()
        _erro(e)
    db.commit()
    return avaliacoes.serializar_completa(db, a, _usuario(request))


def _acao(db, a, request, fn, *args):
    try:
        fn(db, a, _usuario(request), *args)
    except (avaliacoes.Conflito, avaliacoes.Invalida) as e:
        db.rollback()
        _erro(e)
    db.commit()
    return avaliacoes.serializar_completa(db, a, _usuario(request))


@router.post("/avaliacoes/{aid}/finalizar")
def finalizar(aid: int, request: Request, db: Session = Depends(get_db), _u=Depends(monitoria)):
    return _acao(db, _avaliacao(db, aid), request, avaliacoes.finalizar)


class MotivoIn(BaseModel):
    motivo: str = ""


@router.post("/avaliacoes/{aid}/nao-avaliavel")
def nao_avaliavel(aid: int, dados: MotivoIn, request: Request, db: Session = Depends(get_db), _u=Depends(monitoria)):
    return _acao(db, _avaliacao(db, aid), request, avaliacoes.marcar_nao_avaliavel, dados.motivo)


@router.post("/avaliacoes/{aid}/reabrir")
def reabrir(aid: int, dados: MotivoIn, request: Request, db: Session = Depends(get_db), _u=Depends(monitoria)):
    return _acao(db, _avaliacao(db, aid), request, avaliacoes.reabrir, dados.motivo)


@router.delete("/avaliacoes/{aid}/trava")
def liberar(aid: int, request: Request, forcar: bool = False, db: Session = Depends(get_db), _u=Depends(monitoria)):
    u = _usuario(request)
    if forcar and u is not None and u.papel != "admin":
        raise HTTPException(403, "Só um administrador libera a avaliação de outra pessoa.")
    a = _avaliacao(db, aid)
    try:
        avaliacoes.liberar_trava(db, a, u, forcar)
    except avaliacoes.Conflito as e:
        _erro(e)
    db.commit()
    return {"ok": True}
