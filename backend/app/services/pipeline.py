"""Orquestra: análise acústica -> IA -> divergência -> resolução de identidade -> persistência."""
import re
import unicodedata

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Call, ContactIdentity, agora
from ..taxonomy import label_cat
from . import ai_qualifier, audio_analyzer, custos, status


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


TABS_SEM_CONVERSA = ("MUDA_OU_CAIXA", "LIGACAO_MUDA", "CAIXA_POSTAL")


def tem_conversa_no_audio(call: Call) -> str | None:
    """Indício acústico (sem IA) de que houve conversa. Devolve a descrição do indício, ou None."""
    m = call.metricas_acusticas or {}
    if not m.get("vad"):
        return None
    por_canal = m.get("fala_por_canal")
    if por_canal:  # estéreo com as pontas separadas: precisa haver fala dos DOIS lados
        if min(por_canal) >= settings.suspeita_fala_canal_segundos:
            return f"há fala dos dois lados ({por_canal[0]:.0f}s e {por_canal[1]:.0f}s)"
        return None
    fala = m.get("fala_segundos") or 0
    if fala >= settings.suspeita_fala_mono_segundos:
        return f"há {fala:.0f}s de fala no áudio"
    return None


def calcular_divergencia(call: Call) -> None:
    """Compara a tabulação do operador com a qualificação e decide entre três saídas:

    - coerente;
    - DIVERGENTE: só quando a IA tem segurança (categoria definida e confiança mínima);
    - REVISÃO HUMANA: a IA não teve segurança, ou o áudio contradiz a tabulação. Nesses casos
      ninguém é acusado: um supervisor ouve e decide.
    """
    if not call.tabulacao_operador:
        return
    tab = normalizar_tabulacao(call.tabulacao_operador)
    call.tabulacao_normalizada = tab
    indicio = tem_conversa_no_audio(call) if tab in TABS_SEM_CONVERSA else None

    if not call.categoria:  # ainda sem análise: só o indício acústico pode pedir revisão
        call.precisa_revisao = bool(indicio)
        call.revisao_motivo = f"Tabulada como muda/caixa postal, mas {indicio}." if indicio else None
        return

    ia = label_cat(call.categoria)
    div, det = False, None
    if tab == "NAO_TABULADO" and call.categoria in ("EM_NEGOCIACAO", "SEM_INTERESSE", "NAO_E_O_CLIENTE"):
        div = True
        det = f"Operador não tabulou ({call.tabulacao_operador}), mas a IA identificou '{ia}'."
    elif tab == "MUDA_OU_CAIXA":
        div = call.categoria not in ("LIGACAO_MUDA", "CAIXA_POSTAL")
        if div:
            det = f"Operador tabulou '{call.tabulacao_operador}', mas a IA identificou '{ia}'."
    elif tab not in ("NAO_TABULADO", "OUTRO") and tab != call.categoria:
        div = True
        det = f"Operador tabulou '{call.tabulacao_operador}', mas a IA identificou '{ia}'."

    revisar, motivo = False, None
    conf = call.confianca
    if call.categoria == "INDETERMINADO":
        div, det = False, None
        revisar, motivo = True, "A IA não conseguiu classificar esta ligação (áudio ou fala insuficiente)."
    elif div and conf is not None and conf < settings.confianca_minima_divergencia:
        revisar = True
        motivo = f"Possível divergência ('{ia}'), mas a IA teve confiança baixa ({conf:.0%}). Ouça antes de apontar."
        div, det = False, None
    elif (not div and indicio and call.categoria == "LIGACAO_MUDA"
          and call.subcategoria != "FALHA_COMUNICACAO"):  # nessa, os dois lados falam mesmo (e não se ouvem)
        revisar, motivo = True, f"A IA classificou como muda, mas {indicio}."

    call.divergencia_tabulacao, call.divergencia_detalhe = div, det
    call.precisa_revisao, call.revisao_motivo = revisar, motivo


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


def _concluir(db: Session, call: Call, res: "ai_qualifier.Resultado") -> None:
    call.categoria, call.subcategoria = res.categoria, res.subcategoria
    call.confianca, call.resumo, call.evidencia = res.confianca, res.resumo, res.evidencia
    call.transcricao = res.transcricao or call.transcricao
    call.transcricao_diarizada = [t.model_dump() for t in res.turnos] or None
    if res.por_canal:  # reatribui o dicionário para o banco perceber a mudança
        call.metricas_acusticas = {**(call.metricas_acusticas or {}), "transcricao_por_canal": True}
    call.sentimento_cliente = res.sentimento_cliente
    call.motor = res.motor
    call.status, call.erro = "done", None
    call.qualificado_em = agora()
    calcular_divergencia(call)
    db.flush()
    resolver_identidade(db, call)


def _registrar_uso(db: Session, call: Call, uso: list[dict]) -> None:
    for u in uso:
        custos.registrar(db, call, u["tipo"], u["modelo"], u.get("audio_segundos", 0),
                         u.get("tokens_entrada", 0), u.get("tokens_saida", 0), u.get("audio_segundos_original"))


def qualificar_call(db: Session, call: Call, force: bool = False) -> Call:
    if call.status == "done" and not force:
        return call
    try:
        if call.caminho_audio:
            m = audio_analyzer.analyze(call.caminho_audio)
            call.metricas_acusticas = m
            call.duracao_segundos = call.duracao_segundos or m.get("duracao_segundos")
            call.fala_segundos = m.get("fala_segundos")
            # Antes de qualquer IA: "tabulou muda/caixa postal, mas tem conversa" já entra na revisão
            if not call.categoria:
                calcular_divergencia(call)
                db.commit()
            # Sem nenhuma fala detectada: é mudo total. Resolve aqui, de graça, sem transcrever.
            if m.get("vad") and (m.get("fala_segundos") or 0) < settings.vad_fala_minima_segundos:
                _concluir(db, call, ai_qualifier.Resultado(
                    categoria="LIGACAO_MUDA", subcategoria="MUDO_TOTAL", confianca=0.95, motor="local",
                    resumo="Nenhuma fala detectada no áudio (análise local, sem uso de IA).",
                    transcricao=call.transcricao or ""))
                db.commit()
                return call
        if not settings.openai_api_key and not call.transcricao:
            call.status = "awaiting_ai"
            call.erro = "Configure OPENAI_API_KEY para escutar e qualificar o áudio."
            db.commit()
            return call
        if settings.openai_api_key and custos.teto_atingido(db):
            call.status = "awaiting_ai"
            call.erro = (f"Teto diário de IA atingido (US$ {settings.ia_teto_diario_usd:.2f}). "
                         "A ligação será processada automaticamente amanhã.")
            db.commit()
            return call
        res = ai_qualifier.qualificar(call.caminho_audio, call.nome_esperado, call.telefone,
                                      call.duracao_segundos, call.transcricao)
        _registrar_uso(db, call, res.uso)
        _concluir(db, call, res)
        if res.motor == "openai":
            status.registrar(status.IA, True, f"Ligação #{call.id} qualificada", db=db)
    except ai_qualifier.QualificacaoError as e:
        # A IA falhou: não inventa categoria; guarda o que já foi transcrito (e pago) e volta para a fila.
        _registrar_uso(db, call, e.uso)
        if e.transcricao:
            call.transcricao = e.transcricao
        call.status, call.erro = "error", str(e)[:500]
        status.registrar(status.IA, False, f"Ligação #{call.id}: {e}", db=db)
    except Exception as e:
        call.status, call.erro = "error", str(e)[:500]
    db.commit()
    return call
