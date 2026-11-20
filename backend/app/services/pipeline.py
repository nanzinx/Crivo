"""Orquestra: análise acústica -> IA -> divergência -> resolução de identidade -> persistência."""
import re
import unicodedata

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Call, ContactIdentity, Tabulacao, agora
from ..taxonomy import TAXONOMIA_VERSAO, label_cat, label_sub
from . import ai_qualifier, audio_analyzer, custos, qualidade, status, tabulacoes


def _sem_acento(s: str) -> str:
    s = unicodedata.normalize("NFD", s or "")
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def norm_nome(n: str | None) -> str:
    return re.sub(r"[^a-z ]", "", _sem_acento((n or "").lower())).strip()


def normalizar_tabulacao(tabulacao: str | None) -> str:
    """Resumo da SUGESTÃO para um texto de tabulação (sem consultar o catálogo)."""
    return tabulacoes.sugerir(tabulacao).codigo


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
    """Compara um resultado com a regra da tabulação, sem considerar confiança.

    Devolve (diverge, detalhe, pedido_de_nao_ligar_sem_registro). Usada pelo pipeline e pela medição de qualidade.
    """
    if categoria == "INDETERMINADO":
        return False, None, False
    ia = label_cat(categoria)
    tab = tab or "(sem texto)"
    div, det = False, None
    if regra.tipo == "nao_tabulado":
        if categoria in tabulacoes.CONVERSA:
            div, det = True, f"Operador não tabulou ({tab}), mas a IA identificou '{ia}'."
    elif regra.tipo == "resultado" and regra.categorias:
        if categoria not in regra.categorias:
            div, det = True, f"Operador tabulou '{tab}', mas a IA identificou '{ia}'."
        elif regra.subcategoria and subcategoria and subcategoria != regra.subcategoria:
            div = True
            det = (f"Categoria confere, mas a subcategoria não: o operador tabulou '{tab}' "
                   f"({label_sub(categoria, regra.subcategoria)}) e a IA identificou '{label_sub(categoria, subcategoria)}'.")
    pendente = bool(pediu_nao_ligar) and nao_ligar_ativo and not regra.nao_ligar
    if pendente:
        aviso = f"O cliente pediu para não ligar mais, mas a tabulação '{tab}' não registra o pedido."
        div, det = True, f"{det} {aviso}" if det else aviso
    return div, det, pendente


def calcular_divergencia(call: Call, regra: "tabulacoes.Regra | None" = None, nao_ligar_ativo: bool = False) -> None:
    """Compara a tabulação do operador com a qualificação e decide entre três saídas:

    - coerente;
    - DIVERGENTE (com gravidade): só quando a IA tem segurança (categoria definida e confiança mínima);
    - REVISÃO HUMANA: a IA não teve segurança, ou o áudio contradiz a tabulação. Nesses casos
      ninguém é acusado: um supervisor ouve e decide.

    Ligação revisada por humano: o resultado humano vale, sem as travas de confiança.
    `regra` vem do modelo de tabulação (catálogo). Sem ela, usa a sugestão pelo texto.
    `nao_ligar_ativo`: o Argus tem tabulação para registrar o pedido de não ligar.
    """
    if not call.tabulacao_operador and regra is None:
        if call.revisado_em is not None:  # sem tabulação: nada a comparar, mas a revisão encerra a pendência
            call.precisa_revisao, call.revisao_motivo = False, None
        return
    regra = regra or tabulacoes.sugerir(call.tabulacao_operador)
    call.tabulacao_normalizada = regra.codigo
    humano = call.revisado_em is not None
    indicio = tem_conversa_no_audio(call) if regra.sem_contato and not humano else None

    if not call.categoria:  # ainda sem análise: só o indício acústico pode pedir revisão
        call.precisa_revisao = bool(indicio)
        call.revisao_motivo = f"Tabulada como muda/caixa postal, mas {indicio}." if indicio else None
        call.divergencia_tabulacao, call.divergencia_detalhe, call.divergencia_gravidade = False, None, None
        return

    cat, sub = call.categoria, call.subcategoria
    div, det, nao_ligar_pendente = comparar(regra, cat, sub, call.pediu_nao_ligar, nao_ligar_ativo,
                                            call.tabulacao_operador or "")
    if humano and det:
        det = det.replace("a IA identificou", "a revisão humana identificou")

    revisar, motivo = False, None
    conf = call.confianca
    if humano:
        pass  # a revisão humana é o gabarito: não há o que reconferir
    elif cat == "INDETERMINADO":
        revisar, motivo = True, "A IA não conseguiu classificar esta ligação (áudio ou fala insuficiente)."
    elif div and conf is not None and conf < settings.confianca_minima_divergencia:
        revisar = True
        motivo = (f"Possível divergência ('{label_cat(cat)}'), mas a IA teve confiança baixa ({conf:.0%}). "
                  "Ouça antes de apontar.")
        div, det = False, None
    elif (not div and indicio and cat == "LIGACAO_MUDA"
          and sub != "FALHA_COMUNICACAO"):  # nessa, os dois lados falam mesmo (e não se ouvem)
        revisar, motivo = True, f"A IA classificou como muda, mas {indicio}."

    call.divergencia_tabulacao, call.divergencia_detalhe = div, det
    call.divergencia_gravidade = gravidade(regra, cat, nao_ligar_pendente) if div else None
    call.precisa_revisao, call.revisao_motivo = revisar, motivo


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
        antes = (bool(c.divergencia_tabulacao), c.divergencia_gravidade, bool(c.precisa_revisao))
        calcular_divergencia(c, regras.get(c.tabulacao_id), ativo)
        total += 1
        mudaram += antes != (bool(c.divergencia_tabulacao), c.divergencia_gravidade, bool(c.precisa_revisao))
    db.commit()
    return total, mudaram


def vincular_pendentes(db: Session, limite: int = 5000) -> int:
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
    call.categoria_ia, call.subcategoria_ia = res.categoria, res.subcategoria
    if call.revisado_em is None:  # revisão humana prevalece sobre uma reanálise da IA
        call.categoria, call.subcategoria = res.categoria, res.subcategoria
        call.na_amostra = qualidade.na_amostra(call)
    call.confianca, call.resumo, call.evidencia = res.confianca, res.resumo, res.evidencia
    call.transcricao = res.transcricao or call.transcricao
    call.transcricao_diarizada = [t.model_dump() for t in res.turnos] or None
    extras = {}
    if res.por_canal:
        extras["transcricao_por_canal"] = True
    if res.alucinacoes_removidas:
        extras["alucinacoes_removidas"] = res.alucinacoes_removidas
    if extras:  # reatribui o dicionário para o banco perceber a mudança
        call.metricas_acusticas = {**(call.metricas_acusticas or {}), **extras}
    call.sentimento_cliente = res.sentimento_cliente
    call.motor = res.motor
    call.status, call.erro = "done", None
    call.qualificado_em = agora()
    call.pediu_nao_ligar = bool(res.pedido_nao_ligar)
    call.taxonomia_versao = TAXONOMIA_VERSAO
    atualizar_divergencia(db, call)
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
                atualizar_divergencia(db, call)
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
        # Ligação já revisada por humano continua válida: a falha só impede a comparação com a IA.
        call.status, call.erro = ("done" if call.revisado_em else "error"), str(e)[:500]
        status.registrar(status.IA, False, f"Ligação #{call.id}: {e}", db=db)
    except Exception as e:
        call.status, call.erro = ("done" if call.revisado_em else "error"), str(e)[:500]
    db.commit()
    return call
