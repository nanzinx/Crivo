"""Orquestra: gravação -> fila da monitora; resultado da avaliação -> divergência -> identidade."""
import logging
import re
import unicodedata

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..models import Call, ContactIdentity, Tabulacao
from ..taxonomy import label_cat, label_sub
from . import argus_client, avaliacoes, status, tabulacoes

log = logging.getLogger("pipeline")


def _sem_acento(s: str) -> str:
    s = unicodedata.normalize("NFD", s or "")
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def norm_nome(n: str | None) -> str:
    return re.sub(r"[^a-z ]", "", _sem_acento((n or "").lower())).strip()


def normalizar_tabulacao(tabulacao: str | None) -> str:
    """Resumo da SUGESTÃO para um texto de tabulação (sem consultar o catálogo)."""
    return tabulacoes.sugerir(tabulacao).codigo


GRAVIDADES = {
    "alta": "Oportunidade perdida, negociação que não existiu, conversa registrada como sem contato, "
            "ou pedido de não ligar sem registro.",
    "media": "Resultado de conversa trocado, ou conversa registrada onde não houve.",
    "baixa": "Confusão entre muda e caixa postal, ou só a subcategoria diferente.",
}


def gravidade(regra: "tabulacoes.Regra", categoria: str, nao_ligar_pendente: bool = False) -> str:
    """Quão grave é a divergência, pelo impacto no negócio (ver GRAVIDADES)."""
    if nao_ligar_pendente:
        return "alta"
    esperadas = set(regra.categorias)
    if regra.tipo == "nao_tabulado":
        return "alta" if categoria == "EM_NEGOCIACAO" else "media"
    if categoria in esperadas:  # categoria certa, subcategoria diferente
        return "baixa"
    if categoria == "EM_NEGOCIACAO" or "EM_NEGOCIACAO" in esperadas:
        return "alta"
    if regra.sem_contato:
        return "alta" if categoria in tabulacoes.CONVERSA else "baixa"
    return "media"


def comparar(regra: "tabulacoes.Regra", categoria: str, subcategoria: str | None, pediu_nao_ligar: bool | None,
             nao_ligar_ativo: bool, tab: str = "") -> tuple[bool, str | None, bool]:
    """Compara o resultado da ligação com a regra da tabulação.

    Devolve (diverge, detalhe, pedido_de_nao_ligar_sem_registro).
    """
    if categoria == "INDETERMINADO":
        return False, None, False
    res = label_cat(categoria)
    tab = tab or "(sem texto)"
    div, det = False, None
    if regra.tipo == "nao_tabulado":
        if categoria in tabulacoes.CONVERSA:
            div, det = True, f"Operador não tabulou ({tab}), mas a monitoria identificou '{res}'."
    elif regra.tipo == "resultado" and regra.categorias:
        if categoria not in regra.categorias:
            div, det = True, f"Operador tabulou '{tab}', mas a monitoria identificou '{res}'."
        elif regra.subcategoria and subcategoria and subcategoria != regra.subcategoria:
            div = True
            det = (f"Categoria confere, mas a subcategoria não: o operador tabulou '{tab}' "
                   f"({label_sub(categoria, regra.subcategoria)}) e a monitoria identificou '{label_sub(categoria, subcategoria)}'.")
    pendente = bool(pediu_nao_ligar) and nao_ligar_ativo and not regra.nao_ligar
    if pendente:
        aviso = f"O cliente pediu para não ligar mais, mas a tabulação '{tab}' não registra o pedido."
        div, det = True, f"{det} {aviso}" if det else aviso
    return div, det, pendente


def calcular_divergencia(call: Call, regra: "tabulacoes.Regra | None" = None, nao_ligar_ativo: bool = False) -> None:
    """Compara a tabulação do operador com o resultado registrado pela monitora.

    Só a ligação AVALIADA (avaliação finalizada) tem resultado: as demais não contam como divergência e
    aparecem como "não avaliada". Divergente recebe a gravidade (ver GRAVIDADES).
    `regra` vem do modelo de tabulação (catálogo). Sem ela, usa a sugestão pelo texto.
    `nao_ligar_ativo`: o Argus tem tabulação para registrar o pedido de não ligar.
    """
    if not call.tabulacao_operador and regra is None:
        return
    regra = regra or tabulacoes.sugerir(call.tabulacao_operador)
    call.tabulacao_normalizada = regra.codigo
    if call.status != avaliacoes.AVALIADA or not call.categoria:
        call.divergencia_tabulacao, call.divergencia_detalhe, call.divergencia_gravidade = False, None, None
        return
    div, det, nao_ligar_pendente = comparar(regra, call.categoria, call.subcategoria, call.pediu_nao_ligar,
                                            nao_ligar_ativo, call.tabulacao_operador or "")
    call.divergencia_tabulacao, call.divergencia_detalhe = div, det
    call.divergencia_gravidade = gravidade(regra, call.categoria, nao_ligar_pendente) if div else None


def atualizar_divergencia(db: Session, call: Call, nao_ligar_ativo: bool | None = None) -> None:
    """Liga a ligação ao modelo de tabulação (criando a tabulação no catálogo se for nova) e recalcula."""
    row = tabulacoes.obter_ou_criar(db, call.tabulacao_operador, call.id_tabulacao_argus)
    if row is not None:
        call.tabulacao_id = row.id
    ativo = tabulacoes.nao_ligar_ativo(db) if nao_ligar_ativo is None else nao_ligar_ativo
    calcular_divergencia(call, tabulacoes.regra_de(row) if row else None, ativo)


def recalcular(db: Session, tabulacao_ids: set[int] | None = None, incluir_nao_ligar: bool = False) -> tuple[int, int]:
    """Recalcula a divergência das ligações das tabulações indicadas (todas, se None).

    `incluir_nao_ligar`: recalcula também todas as ligações com pedido de não ligar (necessário
    quando muda quais tabulações registram esse pedido). Devolve (recalculadas, mudaram).
    """
    regras = {row.id: tabulacoes.regra_de(row) for row in db.scalars(select(Tabulacao))}
    ativo = any(r.nao_ligar for r in regras.values())
    cond = []
    if tabulacao_ids is None:
        cond.append(Call.tabulacao_id.is_not(None))
    elif tabulacao_ids:
        cond.append(Call.tabulacao_id.in_(tabulacao_ids))
    if incluir_nao_ligar:
        cond.append(Call.pediu_nao_ligar.is_(True))
    if not cond:
        return 0, 0
    total = mudaram = 0
    for c in db.scalars(select(Call).where(or_(*cond))):
        antes = (bool(c.divergencia_tabulacao), c.divergencia_gravidade)
        calcular_divergencia(c, regras.get(c.tabulacao_id), ativo)
        total += 1
        mudaram += antes != (bool(c.divergencia_tabulacao), c.divergencia_gravidade)
    db.commit()
    return total, mudaram


def vincular_pendentes(db: Session, limite: int | None = 5000) -> int:
    """Liga ao catálogo as ligações com tabulação que ainda não estão ligadas (ex.: dados antigos)."""
    calls = db.scalars(select(Call).where(Call.tabulacao_id.is_(None), Call.tabulacao_operador.is_not(None))
                       .limit(limite)).all()
    if not calls:
        return 0
    ativo = tabulacoes.nao_ligar_ativo(db)
    for c in calls:
        atualizar_divergencia(db, c, ativo)
    db.commit()
    return len(calls)


def resolver_identidade(db: Session, call: Call) -> None:
    """Regra 'É o cliente': nega identidade agora, mas já se confirmou antes no mesmo telefone/nome."""
    if not call.telefone:
        return
    nome = norm_nome(call.nome_esperado)
    if call.categoria == "NAO_E_O_CLIENTE" and call.subcategoria not in ("TITULAR_FALECIDO", "CHIP_NOVO"):
        ev = db.scalars(
            select(ContactIdentity).where(ContactIdentity.telefone == call.telefone,
                                          ContactIdentity.nome_normalizado == nome,
                                          ContactIdentity.id_call_evidencia != call.id)
        ).first()
        if ev:
            call.subcategoria = "E_O_CLIENTE_HISTORICO"
            call.conflito_identidade = True
            call.ligacao_referencia_id = ev.id_call_evidencia
    elif call.categoria in ("EM_NEGOCIACAO", "SEM_INTERESSE"):
        exists = db.scalars(select(ContactIdentity).where(
            ContactIdentity.telefone == call.telefone, ContactIdentity.nome_normalizado == nome,
            ContactIdentity.id_call_evidencia == call.id)).first()
        if not exists:
            db.add(ContactIdentity(telefone=call.telefone, nome_normalizado=nome, id_call_evidencia=call.id,
                                   confirmado_em=call.data_ligacao))


def revalidar_identidades(db: Session) -> int:
    """Reaplica a regra em ordem cronológica (útil após importar acervo)."""
    n = 0
    q = select(Call).where(Call.categoria == "NAO_E_O_CLIENTE").order_by(Call.data_ligacao)
    for c in db.scalars(q):
        before = c.subcategoria
        resolver_identidade(db, c)
        n += before != c.subcategoria
    db.commit()
    return n


def duracao_audio(caminho: str | None) -> float | None:
    """Duração da gravação em segundos (lida pelo mutagen, sem decodificar o áudio). None se ilegível."""
    if not caminho:
        return None
    try:
        import mutagen

        f = mutagen.File(caminho)
        return round(float(f.info.length), 2) if f is not None and f.info and f.info.length else None
    except Exception:  # arquivo ausente, corrompido ou formato desconhecido
        return None


def preparar_call(db: Session, call: Call, baixar_de_novo: bool = False) -> Call:
    """Deixa a ligação pronta para a monitora: baixa a gravação do Argus (se preciso) e põe na fila de avaliação.

    `baixar_de_novo`: baixa a gravação mesmo que já exista (ex.: arquivo corrompido). Não desfaz a avaliação.
    """
    do_argus = call.origem == "argus" and call.id_campanha and call.id_ligacao
    if do_argus and (baixar_de_novo or not call.caminho_audio):
        try:
            call.caminho_audio = str(argus_client.download_gravacao(call.id_campanha, call.id_ligacao))
            status.registrar(status.DOWNLOAD, True, f"Ligação #{call.id}", db=db)
        except Exception as e:
            call.erro = f"download: {str(e)[:300]}"
            if call.status not in avaliacoes.FINALIZADAS:
                call.status = avaliacoes.ERRO
            db.commit()
            status.registrar(status.DOWNLOAD, False, f"Ligação #{call.id}: {e}", db=db)
            return call
    if call.caminho_audio:
        if not call.duracao_segundos:
            call.duracao_segundos = duracao_audio(call.caminho_audio)
        call.erro = None
        if call.status in (avaliacoes.PENDENTE, avaliacoes.ERRO, None):
            call.status = avaliacoes.PENDENTE_AVALIACAO
    db.commit()
    return call
