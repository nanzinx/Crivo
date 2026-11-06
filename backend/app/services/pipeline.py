"""Orquestra: análise acústica -> IA -> divergência -> resolução de identidade -> persistência."""
import re
import unicodedata

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Call, ContactIdentity, agora
from . import ai_qualifier, audio_analyzer, status


def _sem_acento(s: str) -> str:
    s = unicodedata.normalize("NFD", s or "")
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def norm_nome(n: str | None) -> str:
    return re.sub(r"[^a-z ]", "", _sem_acento((n or "").lower())).strip()


def normalizar_tabulacao(tabulacao: str | None) -> str:
    """Converte o texto livre da tabulação do Argus para o código de categoria comparável com a IA.

    Fonte única desta regra (antes havia duas cópias divergentes). Na semana 2 ela deve ser
    substituída por uma tabela de equivalência por ID de tabulação do Argus.
    """
    t = _sem_acento(tabulacao or "").upper()
    if "NEGOCIA" in t or "CONTRATO" in t:
        return "EM_NEGOCIACAO"
    if "NAO E O CLIENTE" in t or "ENGANO" in t:
        return "NAO_E_O_CLIENTE"
    if "NAO TEM INTERESSE" in t or "SEM INTERESSE" in t or "NAO QUER" in t:
        return "SEM_INTERESSE"
    if "MUDA" in t and "CAIXA" in t:
        return "MUDA_OU_CAIXA"
    if "MUDA" in t:
        return "LIGACAO_MUDA"
    if "CAIXA" in t or "SECRETARIA" in t:
        return "CAIXA_POSTAL"
    if "TEMPO POS" in t or "NAO TABULADO" in t or not t.strip():
        return "NAO_TABULADO"
    return "OUTRO"


def calcular_divergencia(call: Call) -> None:
    """Compara o que o operador tabulou com a qualificação da IA e documenta a divergência."""
    if not call.tabulacao_operador:
        return
    tab = normalizar_tabulacao(call.tabulacao_operador)
    call.tabulacao_normalizada = tab
    if not call.categoria:
        return
    div, det = False, None
    if tab == "NAO_TABULADO" and call.categoria in ("EM_NEGOCIACAO", "SEM_INTERESSE", "NAO_E_O_CLIENTE"):
        div = True
        det = f"Operador não tabulou ({call.tabulacao_operador}), mas IA identificou {call.categoria}."
    elif tab == "MUDA_OU_CAIXA":
        div = call.categoria not in ("LIGACAO_MUDA", "CAIXA_POSTAL")
        if div:
            det = f"Operador tabulou '{call.tabulacao_operador}', mas IA identificou '{call.categoria}'."
    elif tab not in ("NAO_TABULADO", "OUTRO") and tab != call.categoria:
        div = True
        det = f"Operador tabulou '{call.tabulacao_operador}', mas IA identificou '{call.categoria}'."
    call.divergencia_tabulacao, call.divergencia_detalhe = div, det


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
            call.resumo = (call.resumo or "") + " | Titular já se identificou em outra ligação."
    elif call.categoria in ("EM_NEGOCIACAO", "SEM_INTERESSE") and (call.confianca or 0) >= 0.6:
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


def qualificar_call(db: Session, call: Call, force: bool = False) -> Call:
    if call.status == "done" and not force:
        return call
    try:
        if call.caminho_audio:
            m = audio_analyzer.analyze(call.caminho_audio)
            call.metricas_acusticas = m
            call.duracao_segundos = call.duracao_segundos or m.get("duracao_segundos")
        if not settings.openai_api_key and not call.transcricao:
            call.status = "awaiting_ai"
            call.erro = "Configure OPENAI_API_KEY para escutar e qualificar o áudio."
            db.commit()
            return call
        res = ai_qualifier.qualificar(call.caminho_audio, call.nome_esperado, call.telefone,
                                      call.duracao_segundos, call.transcricao)
        call.categoria, call.subcategoria = res.categoria, res.subcategoria
        call.confianca, call.resumo, call.evidencia = res.confianca, res.resumo, res.evidencia
        call.transcricao = res.transcricao or call.transcricao
        call.transcricao_diarizada = [t.model_dump() for t in res.turnos] or None
        call.sentimento_cliente = res.sentimento_cliente
        call.motor = res.motor
        call.status, call.erro = "done", None
        call.qualificado_em = agora()
        calcular_divergencia(call)
        db.flush()
        resolver_identidade(db, call)
        if res.motor == "openai":
            status.registrar(status.IA, True, f"Ligação #{call.id} qualificada", db=db)
    except ai_qualifier.QualificacaoError as e:
        # A IA falhou: não inventa categoria; guarda o que já foi transcrito e volta para a fila.
        if e.transcricao:
            call.transcricao = e.transcricao
        call.status, call.erro = "error", str(e)[:500]
        status.registrar(status.IA, False, f"Ligação #{call.id}: {e}", db=db)
    except Exception as e:
        call.status, call.erro = "error", str(e)[:500]
    db.commit()
    return call
