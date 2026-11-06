"""Orquestra: análise acústica -> IA -> resolução de identidade -> persistência."""
import re
import unicodedata
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Call, ContactIdentity
from . import ai_qualifier, audio_analyzer


def norm_nome(n: str | None) -> str:
    n = unicodedata.normalize("NFD", (n or "").lower())
    n = "".join(c for c in n if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z ]", "", n).strip()


def calcular_divergencia(call: Call) -> None:
    """Verifica e documenta divergência entre o que o operador tabulou e a qualificação da IA."""
    if not call.tabulacao_operador:
        return
    t_up = unicodedata.normalize("NFD", call.tabulacao_operador.lower())
    t_up = "".join(c for c in t_up if unicodedata.category(c) != "Mn").upper()
    tab_norm = "OUTRO"
    if "NEGOCIA" in t_up or "CONTRATO" in t_up:
        tab_norm = "EM_NEGOCIACAO"
    elif "NAO E O CLIENTE" in t_up or "ENGANO" in t_up:
        tab_norm = "NAO_E_O_CLIENTE"
    elif "NAO TEM INTERESSE" in t_up or "SEM INTERESSE" in t_up or "NAO QUER" in t_up:
        tab_norm = "SEM_INTERESSE"
    elif "MUDA" in t_up and "CAIXA" in t_up:
        tab_norm = "MUDA_OU_CAIXA"
    elif "MUDA" in t_up:
        tab_norm = "LIGACAO_MUDA"
    elif "CAIXA" in t_up or "SECRETARIA" in t_up:
        tab_norm = "CAIXA_POSTAL"
    elif "TEMPO POS" in t_up or "NAO TABULADO" in t_up or not t_up.strip():
        tab_norm = "NAO_TABULADO"

    call.tabulacao_normalizada = tab_norm
    if call.categoria:
        if tab_norm == "NAO_TABULADO" and call.categoria in ("EM_NEGOCIACAO", "SEM_INTERESSE", "NAO_E_O_CLIENTE"):
            call.divergencia_tabulacao = True
            call.divergencia_detalhe = f"Operador não tabulou ({call.tabulacao_operador}), mas IA identificou {call.categoria}."
        elif tab_norm == "MUDA_OU_CAIXA" and call.categoria in ("LIGACAO_MUDA", "CAIXA_POSTAL"):
            call.divergencia_tabulacao = False
            call.divergencia_detalhe = None
        elif tab_norm not in ("NAO_TABULADO", "OUTRO", "MUDA_OU_CAIXA") and tab_norm != call.categoria:
            call.divergencia_tabulacao = True
            call.divergencia_detalhe = f"Operador tabulou '{call.tabulacao_operador}', mas IA identificou '{call.categoria}'."
        else:
            call.divergencia_tabulacao = False
            call.divergencia_detalhe = None


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
        call.qualificado_em = datetime.utcnow()
        calcular_divergencia(call)
        db.flush()
        resolver_identidade(db, call)
    except Exception as e:
        call.status, call.erro = "error", str(e)[:500]
    db.commit()
    return call
