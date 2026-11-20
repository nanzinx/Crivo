"""Modelo de tabulação: o que cada tabulação do Argus significa na taxonomia do Crivo.

Fluxo:
1. Toda tabulação que chega (webhook, polling, relatório da discadora) entra no catálogo com um
   significado SUGERIDO a partir do texto (`sugerir`).
2. A equipe confirma ou corrige na tela "Modelo de tabulação" (ou importa uma planilha).
3. A divergência (pipeline.calcular_divergencia) usa a regra do catálogo; ao editar, as ligações
   daquela tabulação são recalculadas.

Uma regra diz:
- `tipo`: "resultado" (afirma um resultado), "nao_tabulado" (operador não registrou resultado,
  ex.: tempo pós-atendimento) ou "ignorar" (não comparável: tabulações de sistema, pausas...).
- `categorias`: as categorias da IA aceitas como coerentes. Mais de uma quando o Argus é mais
  genérico que a taxonomia (ex.: "Muda / Caixa postal").
- `subcategoria`: opcional; quando definida, a subcategoria também precisa bater.
- `nao_ligar`: esta tabulação registra o pedido do cliente de não receber mais ligações.
"""
import re
import unicodedata
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import Tabulacao

TIPOS = {
    "resultado": "Resultado",
    "nao_tabulado": "Não tabulado",
    "ignorar": "Ignorar na comparação",
}
CONVERSA = {"EM_NEGOCIACAO", "NAO_E_O_CLIENTE", "SEM_INTERESSE"}  # houve contato humano
SEM_CONTATO = {"LIGACAO_MUDA", "CAIXA_POSTAL"}


@dataclass
class Regra:
    tipo: str
    categorias: list[str] = field(default_factory=list)
    subcategoria: str | None = None
    nao_ligar: bool = False
    confirmada: bool = False
    id: int | None = None

    @property
    def codigo(self) -> str:
        """Resumo da regra (guardado em Call.tabulacao_normalizada para filtros e telas)."""
        if self.tipo == "nao_tabulado":
            return "NAO_TABULADO"
        if self.tipo == "ignorar" or not self.categorias:
            return "OUTRO"
        if set(self.categorias) == SEM_CONTATO:
            return "MUDA_OU_CAIXA"
        return self.categorias[0] if len(self.categorias) == 1 else "VARIAS"

    @property
    def sem_contato(self) -> bool:
        """A tabulação afirma que não houve conversa com uma pessoa."""
        return self.tipo == "resultado" and bool(self.categorias) and set(self.categorias) <= SEM_CONTATO


def chave(texto: str | None) -> str:
    """Normaliza o texto da tabulação: sem acento, maiúsculo, só letras/números separados por espaço."""
    t = unicodedata.normalize("NFD", texto or "")
    t = "".join(c for c in t if unicodedata.category(c) != "Mn").upper()
    return re.sub(r"[^A-Z0-9]+", " ", t).strip()


def _tem(t: str, *termos: str) -> bool:
    return any(x in t for x in termos)


def sugerir(texto: str | None) -> Regra:
    """Primeiro palpite pelo texto. É só sugestão: a equipe confirma ou corrige na tela."""
    t = chave(texto)
    r = lambda cats, sub=None, **kw: Regra("resultado", list(cats), sub, **kw)  # noqa: E731
    if not t or _tem(t, "TEMPO POS", "NAO TABULAD", "SEM TABULAC"):
        return Regra("nao_tabulado")
    if _tem(t, "NAO LIGAR", "NAO PERTURBE", "BLOQUE", "REMOVER", "OPT OUT", "NAO QUER RECEBER"):
        return r(["SEM_INTERESSE", "NAO_E_O_CLIENTE"], nao_ligar=True)
    if _tem(t, "FALECID", "OBITO"):
        return r(["NAO_E_O_CLIENTE"], "TITULAR_FALECIDO")
    if _tem(t, "WHATS"):
        return r(["EM_NEGOCIACAO"], "MIGRACAO_WHATSAPP")
    if _tem(t, "AGEND", "RETORN"):
        return r(["EM_NEGOCIACAO"], "AGENDAMENTO_RETORNO")
    if _tem(t, "NEGOCIA", "CONTRATO", "PROPOSTA", "VENDA", "ACEIT"):
        return r(["EM_NEGOCIACAO"])
    if _tem(t, "NAO E O CLIENTE", "ENGANO", "NUMERO ERRADO", "DESCONHEC", "TERCEIRO"):
        return r(["NAO_E_O_CLIENTE"])
    if _tem(t, "NAO TEM INTERESSE", "SEM INTERESSE", "NAO QUER", "RECUS"):
        return r(["SEM_INTERESSE"])
    if "MUDA" in t and _tem(t, "CAIXA", "SECRETARIA"):
        return r(["LIGACAO_MUDA", "CAIXA_POSTAL"])
    if _tem(t, "CAIU", "QUEDA"):
        return r(["LIGACAO_MUDA"], "LIGACAO_CAIU")
    if _tem(t, "MUDA", "SEM AUDIO", "SILENCIO"):
        return r(["LIGACAO_MUDA"])
    if _tem(t, "CAIXA", "SECRETARIA", "RECADO"):
        return r(["CAIXA_POSTAL"])
    return Regra("ignorar")


def regra_de(row: Tabulacao) -> Regra:
    return Regra(row.tipo, list(row.categorias or []), row.subcategoria, bool(row.nao_ligar), bool(row.confirmada), row.id)


def obter_ou_criar(db: Session, texto: str | None, id_argus: int | None = None) -> Tabulacao | None:
    """Acha a tabulação no catálogo (pelo ID do Argus, depois pelo texto) ou cria com a sugestão."""
    if not texto and not id_argus:
        return None
    row = db.scalars(select(Tabulacao).where(Tabulacao.id_argus == id_argus)).first() if id_argus else None
    k = chave(texto) or f"ID {id_argus}"
    if row is None:
        row = db.scalars(select(Tabulacao).where(Tabulacao.chave == k)).first()
        if row is not None and id_argus and row.id_argus is None:
            row.id_argus = id_argus
            db.flush()  # a sessão não grava sozinha: sem isto, a próxima busca pelo ID não acharia
    if row is not None:
        return row
    s = sugerir(texto)
    novo = Tabulacao(chave=k, nome=(texto or "").strip() or f"Tabulação {id_argus}", id_argus=id_argus, tipo=s.tipo,
                     categorias=s.categorias, subcategoria=s.subcategoria, nao_ligar=s.nao_ligar, confirmada=False)
    try:
        with db.begin_nested():  # outra thread pode ter criado a mesma tabulação ao mesmo tempo
            db.add(novo)
            db.flush()
        return novo
    except IntegrityError:
        return db.scalars(select(Tabulacao).where(Tabulacao.chave == k)).first()


def nao_ligar_ativo(db: Session) -> bool:
    """Existe alguma tabulação para registrar o pedido de não ligar? Sem ela, cobrar o operador seria injusto."""
    return db.scalar(select(Tabulacao.id).where(Tabulacao.nao_ligar.is_(True)).limit(1)) is not None


def regras_por_chave(db: Session) -> dict[str, Regra]:
    return {row.chave: regra_de(row) for row in db.scalars(select(Tabulacao))}
