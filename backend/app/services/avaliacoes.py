"""Avaliação humana da ligação (monitoria de qualidade): de onde vem o resultado da ligação.

Ciclo de vida da ligação (Call.status):
    pendente            -> chegou, aguardando o download da gravação
    pendente_avaliacao  -> gravação disponível, na fila da monitora
    em_avaliacao        -> uma monitora está avaliando (rascunho; tela completa na fase 2)
    avaliada            -> avaliação finalizada: categoria/subcategoria valem e entram na divergência
    nao_avaliavel       -> a monitora não conseguiu avaliar (áudio ruim, cortado...): sem resultado
    erro                -> falha no download da gravação (pode baixar de novo)
"""
from sqlalchemy.orm import Session

from ..models import Avaliacao, Call, ContactIdentity, Usuario, agora
from ..taxonomy import TAXONOMIA_VERSAO

PENDENTE = "pendente"
PENDENTE_AVALIACAO = "pendente_avaliacao"
EM_AVALIACAO = "em_avaliacao"
AVALIADA = "avaliada"
NAO_AVALIAVEL = "nao_avaliavel"
ERRO = "erro"
STATUS = (PENDENTE, PENDENTE_AVALIACAO, EM_AVALIACAO, AVALIADA, NAO_AVALIAVEL, ERRO)
FINALIZADAS = (AVALIADA, NAO_AVALIAVEL)  # a monitora já deu o veredito
NAO_AVALIADAS = (PENDENTE, PENDENTE_AVALIACAO, EM_AVALIACAO, ERRO)

ORIGENS = ("tela", "importada", "migrada")


def registrar_resultado(db: Session, call: Call, categoria: str | None, subcategoria: str | None = None,
                        pediu_nao_ligar: bool = False, nao_avaliavel: bool = False, motivo: str | None = None,
                        usuario: Usuario | None = None, monitora_nome: str | None = None,
                        origem: str = "tela") -> Avaliacao:
    """Cria (ou atualiza) a avaliação finalizada da ligação e copia o resultado para a ligação.

    Recalcula a divergência com a tabulação do operador e a regra "É o cliente".
    """
    from . import pipeline

    t = agora()
    a = db.get(Avaliacao, call.avaliacao_id) if call.avaliacao_id else None
    if a is None:
        a = Avaliacao(call_id=call.id, iniciada_em=t)
        db.add(a)
    a.origem = origem
    a.monitora_id = usuario.id if usuario else None
    a.monitora_nome = ((usuario.nome if usuario else monitora_nome) or "Acesso local")[:80]
    a.status = "nao_avaliavel" if nao_avaliavel else "finalizada"
    a.categoria, a.subcategoria = (None, None) if nao_avaliavel else (categoria, subcategoria)
    a.pediu_nao_ligar = bool(pediu_nao_ligar) and not nao_avaliavel
    a.nao_avaliavel_motivo = ((motivo or "").strip()[:1000] or None) if nao_avaliavel else None
    a.finalizada_em = a.atualizado_em = t
    db.flush()

    call.avaliacao_id = a.id
    call.status = NAO_AVALIAVEL if nao_avaliavel else AVALIADA
    call.categoria, call.subcategoria = a.categoria, a.subcategoria
    call.pediu_nao_ligar = a.pediu_nao_ligar
    call.taxonomia_versao = TAXONOMIA_VERSAO
    call.conflito_identidade, call.ligacao_referencia_id = False, None
    call.erro = None
    # resultado corrigido: a confirmação de titularidade que esta ligação dava pode não valer mais
    db.query(ContactIdentity).filter(ContactIdentity.id_call_evidencia == call.id).delete()
    pipeline.atualizar_divergencia(db, call)
    db.flush()
    pipeline.resolver_identidade(db, call)
    return a


def serializar(a: Avaliacao | None) -> dict | None:
    if a is None:
        return None
    iso = lambda d: d.isoformat() if d else None  # noqa: E731
    return {"id": a.id, "status": a.status, "origem": a.origem, "monitora_id": a.monitora_id,
            "monitora_nome": a.monitora_nome, "categoria": a.categoria, "subcategoria": a.subcategoria,
            "pediu_nao_ligar": bool(a.pediu_nao_ligar), "nao_avaliavel_motivo": a.nao_avaliavel_motivo,
            "iniciada_em": iso(a.iniciada_em), "finalizada_em": iso(a.finalizada_em)}
