"""Avaliação humana da ligação (monitoria de qualidade): de onde vem o resultado da ligação.

Ciclo de vida da ligação (Call.status):
    pendente            -> chegou, aguardando o download da gravação
    pendente_avaliacao  -> gravação disponível, na fila da monitora
    em_avaliacao        -> uma monitora está avaliando o script (rascunho com trava)
    avaliada            -> avaliação finalizada: categoria/subcategoria valem e entram na divergência
    nao_avaliavel       -> a monitora não conseguiu avaliar (áudio ruim, cortado...): sem resultado
    erro                -> falha no download da gravação (pode baixar de novo)
"""
from datetime import datetime, timedelta

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from ..models import (Avaliacao, AvaliacaoEvento, AvaliacaoItem, AvaliacaoMarca, Call, ContactIdentity, ScriptItem,
                      ScriptSecao, ScriptVersao, Usuario, agora)
from ..taxonomy import TAXONOMIA_VERSAO, valid

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
    """Registro rápido: cria (ou atualiza) a avaliação finalizada só com o resultado da ligação.

    Recalcula a divergência com a tabulação do operador e a regra "É o cliente".
    """
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
    a.trava_usuario_id = a.trava_nome = a.trava_ate = None
    db.flush()
    _aplicar_na_ligacao(db, call, a)
    return a


def _aplicar_na_ligacao(db: Session, call: Call, a: Avaliacao) -> None:
    """Copia o resultado da avaliação para a ligação e recalcula divergência e identidade."""
    from . import pipeline

    call.avaliacao_id = a.id
    if a.status == "finalizada":
        call.status = AVALIADA
    elif a.status == "nao_avaliavel":
        call.status = NAO_AVALIAVEL
    else:
        call.status = EM_AVALIACAO
    vale = a.status == "finalizada"
    call.categoria, call.subcategoria = (a.categoria, a.subcategoria) if vale else (None, None)
    call.pediu_nao_ligar = bool(a.pediu_nao_ligar) if vale else False
    call.taxonomia_versao = TAXONOMIA_VERSAO
    call.conflito_identidade, call.ligacao_referencia_id = False, None
    call.erro = None
    # resultado mudou: a confirmação de titularidade que esta ligação dava pode não valer mais
    db.query(ContactIdentity).filter(ContactIdentity.id_call_evidencia == call.id).delete()
    pipeline.atualizar_divergencia(db, call)
    db.flush()
    if vale:
        pipeline.resolver_identidade(db, call)


# --------------------------------------------------------------------------- avaliação do script (fase 2)
TRAVA_MINUTOS = 15
DESFECHOS = {"venda": "Houve venda", "recusa": "Houve recusa", "outro": "Conversa sem venda nem recusa",
             "sem_conversa": "Sem conversa (muda, caixa postal, não é o cliente...)"}
ESTADOS = ("acertou", "errou", "divergencia", "nao_se_aplica")
TIPOS_MARCA = ("acertou", "errou", "divergencia", "nota")


class Conflito(Exception):
    """Outra monitora está com a avaliação, ou o estado não permite a ação (vira HTTP 409)."""


class Invalida(Exception):
    """A avaliação não pode ser finalizada: `problemas` diz o que falta (vira HTTP 422)."""

    def __init__(self, problemas: list[str]):
        super().__init__("; ".join(problemas))
        self.problemas = problemas


def _quem(usuario: Usuario | None) -> tuple[int | None, str]:
    return (usuario.id if usuario else None), ((usuario.nome if usuario else None) or "Acesso local")[:80]


def _evento(db: Session, a: Avaliacao, usuario: Usuario | None, acao: str, detalhe: dict | None = None) -> None:
    uid, nome = _quem(usuario)
    db.add(AvaliacaoEvento(avaliacao_id=a.id, usuario_id=uid, usuario_nome=nome, acao=acao, detalhe=detalhe))


def trava_ativa(a: Avaliacao, now: datetime | None = None) -> bool:
    return a.trava_ate is not None and a.trava_ate > (now or agora())


def e_minha(a: Avaliacao, usuario: Usuario | None) -> bool:
    uid, _ = _quem(usuario)
    return a.trava_usuario_id == uid


def _pegar_trava(db: Session, a: Avaliacao, usuario: Usuario | None) -> None:
    """Trava atômica (UPDATE condicional): só pega se estiver livre, vencida ou já for de quem pede."""
    uid, nome = _quem(usuario)
    now = agora()
    dono = Avaliacao.trava_usuario_id == uid if uid is not None else Avaliacao.trava_usuario_id.is_(None)
    r = db.execute(
        update(Avaliacao)
        .where(Avaliacao.id == a.id, or_(Avaliacao.trava_ate.is_(None), Avaliacao.trava_ate < now, dono))
        .values(trava_usuario_id=uid, trava_nome=nome, trava_ate=now + timedelta(minutes=TRAVA_MINUTOS))
        .execution_options(synchronize_session=False)
    )
    if r.rowcount != 1:
        db.refresh(a)
        raise Conflito(f"{a.trava_nome or 'Outra monitora'} está avaliando esta ligação agora.")
    db.refresh(a)


def iniciar(db: Session, call: Call, usuario: Usuario | None) -> Avaliacao:
    """Abre (ou retoma) o rascunho da avaliação do script desta ligação e pega a trava."""
    from . import script

    if call.status in (PENDENTE, ERRO) and not call.caminho_audio:
        raise Conflito("A gravação desta ligação ainda não foi baixada.")
    a = db.get(Avaliacao, call.avaliacao_id) if call.avaliacao_id else None
    if a is not None and a.status != "rascunho":
        raise Conflito("Esta ligação já foi avaliada. Para alterar, reabra a avaliação.")
    if a is None:
        v = script.ativo(db)
        if v is None:
            raise Conflito("Nenhum script ativo. Publique um script antes de avaliar.")
        uid, nome = _quem(usuario)
        a = Avaliacao(call_id=call.id, status="rascunho", origem="tela", script_versao_id=v.id,
                      monitora_id=uid, monitora_nome=nome, iniciada_em=agora())
        db.add(a)
        db.flush()
        # duas monitoras clicando ao mesmo tempo: só um rascunho vira o da ligação
        r = db.execute(update(Call).where(Call.id == call.id, Call.avaliacao_id.is_(None))
                       .values(avaliacao_id=a.id, status=EM_AVALIACAO).execution_options(synchronize_session=False))
        if r.rowcount != 1:
            db.rollback()
            db.refresh(call)
            return iniciar(db, call, usuario)
        db.refresh(call)
        _evento(db, a, usuario, "iniciada")
    elif a.script_versao_id is None:
        v = script.ativo(db)
        if v is None:
            raise Conflito("Nenhum script ativo. Publique um script antes de avaliar.")
        a.script_versao_id = v.id
    _pegar_trava(db, a, usuario)
    uid, nome = _quem(usuario)
    a.monitora_id, a.monitora_nome = uid, nome
    if call.status == PENDENTE_AVALIACAO:
        call.status = EM_AVALIACAO
    return a


def _exigir_rascunho_meu(a: Avaliacao, usuario: Usuario | None) -> None:
    if a.status != "rascunho":
        raise Conflito("A avaliação já foi finalizada. Reabra para alterar.")
    if trava_ativa(a) and not e_minha(a, usuario):
        raise Conflito(f"{a.trava_nome or 'Outra monitora'} está avaliando esta ligação agora.")


def salvar(db: Session, a: Avaliacao, usuario: Usuario | None, dados: dict) -> Avaliacao:
    """Autosave do rascunho. Renova a trava. `itens` e `marcas`, quando vêm, substituem os anteriores."""
    _exigir_rascunho_meu(a, usuario)
    _pegar_trava(db, a, usuario)
    for campo in ("desfecho", "categoria", "subcategoria", "pediu_nao_ligar", "observacao", "feedback_fortes",
                  "feedback_melhorar"):
        if campo in dados:
            setattr(a, campo, dados[campo])
    if "itens" in dados:
        validos = _itens_da_versao(db, a.script_versao_id)
        atuais = {i.item_id: i for i in db.scalars(select(AvaliacaoItem).where(AvaliacaoItem.avaliacao_id == a.id))}
        for it in dados["itens"]:
            iid = it["item_id"]
            if iid not in validos:
                raise Conflito(f"O item {iid} não é desta versão do script.")
            row = atuais.get(iid) or AvaliacaoItem(avaliacao_id=a.id, item_id=iid)
            row.estado, row.comentario = it.get("estado"), (it.get("comentario") or "").strip() or None
            if row.id is None:
                db.add(row)
                atuais[iid] = row
    if "marcas" in dados:
        validos = _itens_da_versao(db, a.script_versao_id)
        db.query(AvaliacaoMarca).filter(AvaliacaoMarca.avaliacao_id == a.id).delete(synchronize_session=False)
        for m in dados["marcas"]:
            if m.get("item_id") is not None and m["item_id"] not in validos:
                raise Conflito(f"O item {m['item_id']} não é desta versão do script.")
            db.add(AvaliacaoMarca(avaliacao_id=a.id, item_id=m.get("item_id"), segundos=max(0.0, float(m["segundos"])),
                                  tipo=m.get("tipo") or "nota", texto=(m.get("texto") or "").strip() or None))
    a.atualizado_em = agora()
    db.flush()
    return a


def _itens_da_versao(db: Session, versao_id: int | None) -> dict[int, tuple[ScriptItem, ScriptSecao]]:
    if versao_id is None:
        return {}
    rows = db.execute(select(ScriptItem, ScriptSecao).join(ScriptSecao, ScriptItem.secao_id == ScriptSecao.id)
                      .where(ScriptSecao.versao_id == versao_id)).all()
    return {i.id: (i, s) for i, s in rows}


def secao_aplica(aplicabilidade: str, desfecho: str | None) -> bool:
    if desfecho == "sem_conversa":
        return False
    if aplicabilidade == "venda":
        return desfecho == "venda"
    if aplicabilidade == "recusa":
        return desfecho == "recusa"
    return True


def calcular(db: Session, a: Avaliacao) -> dict:
    """Nota = Σ peso × valor ÷ Σ pesos dos itens aplicáveis (acertou 1, divergência = valor da versão, errou 0).

    "Não se aplica" e seções fora do caso (venda/recusa) saem da conta. Item crítico errado = falha crítica
    (só sinaliza; não zera a nota).
    """
    v = db.get(ScriptVersao, a.script_versao_id) if a.script_versao_id else None
    itens = _itens_da_versao(db, a.script_versao_id)
    marc = {i.item_id: i for i in db.scalars(select(AvaliacaoItem).where(AvaliacaoItem.avaliacao_id == a.id))}
    valor = {"acertou": 1.0, "errou": 0.0, "divergencia": v.valor_divergencia if v else 0.5}
    soma = pesos = 0.0
    pendentes, sem_comentario, criticos = [], [], []
    contagem = {e: 0 for e in ESTADOS}
    for iid, (item, sec) in itens.items():
        if not secao_aplica(sec.aplicabilidade, a.desfecho):
            continue
        m = marc.get(iid)
        estado = m.estado if m else None
        if estado is None:
            pendentes.append(iid)
            continue
        contagem[estado] = contagem.get(estado, 0) + 1
        if estado in ("errou", "divergencia") and not (m.comentario or "").strip():
            sem_comentario.append(iid)
        if estado == "nao_se_aplica":
            continue
        soma += item.peso * valor[estado]
        pesos += item.peso
        if estado == "errou" and item.critico:
            criticos.append(iid)
    return {"nota": round(100 * soma / pesos, 1) if pesos else None, "falha_critica": bool(criticos),
            "itens_criticos_errados": criticos, "pendentes": pendentes, "sem_comentario": sem_comentario,
            "contagem": contagem}


def finalizar(db: Session, a: Avaliacao, usuario: Usuario | None) -> Avaliacao:
    _exigir_rascunho_meu(a, usuario)
    calc = calcular(db, a)
    problemas = []
    if a.desfecho not in DESFECHOS:
        problemas.append("Escolha o desfecho da ligação (venda, recusa, outro ou sem conversa).")
    if not a.categoria or not valid(a.categoria, a.subcategoria):
        problemas.append("Escolha o resultado da ligação (categoria).")
    if calc["pendentes"]:
        problemas.append(f"Faltam {len(calc['pendentes'])} item(ns) do script para marcar.")
    if calc["sem_comentario"]:
        problemas.append(f"{len(calc['sem_comentario'])} item(ns) com erro ou divergência sem comentário.")
    if problemas:
        raise Invalida(problemas)
    uid, nome = _quem(usuario)
    a.monitora_id, a.monitora_nome = uid, nome
    a.status, a.nota, a.falha_critica = "finalizada", calc["nota"], calc["falha_critica"]
    a.nao_avaliavel_motivo = None
    a.finalizada_em = a.atualizado_em = agora()
    a.trava_usuario_id = a.trava_nome = a.trava_ate = None
    _evento(db, a, usuario, "finalizada", {"nota": a.nota, "falha_critica": a.falha_critica, "categoria": a.categoria})
    db.flush()
    _aplicar_na_ligacao(db, db.get(Call, a.call_id), a)
    return a


def marcar_nao_avaliavel(db: Session, a: Avaliacao, usuario: Usuario | None, motivo: str) -> Avaliacao:
    _exigir_rascunho_meu(a, usuario)
    if not (motivo or "").strip():
        raise Invalida(["Informe por que a ligação não pode ser avaliada."])
    uid, nome = _quem(usuario)
    a.monitora_id, a.monitora_nome = uid, nome
    a.status, a.nao_avaliavel_motivo = "nao_avaliavel", motivo.strip()[:1000]
    a.nota, a.falha_critica = None, False
    a.finalizada_em = a.atualizado_em = agora()
    a.trava_usuario_id = a.trava_nome = a.trava_ate = None
    _evento(db, a, usuario, "nao_avaliavel", {"motivo": a.nao_avaliavel_motivo})
    db.flush()
    _aplicar_na_ligacao(db, db.get(Call, a.call_id), a)
    return a


def reabrir(db: Session, a: Avaliacao, usuario: Usuario | None, motivo: str) -> Avaliacao:
    """Volta a avaliação finalizada para rascunho, guardando na auditoria como ela estava."""
    from . import script

    if a.status == "rascunho":
        raise Conflito("A avaliação já está aberta.")
    if not (motivo or "").strip():
        raise Invalida(["Informe o motivo da reabertura."])
    antes = {"status": a.status, "nota": a.nota, "falha_critica": a.falha_critica, "categoria": a.categoria,
             "subcategoria": a.subcategoria, "monitora": a.monitora_nome,
             "finalizada_em": a.finalizada_em.isoformat() if a.finalizada_em else None}
    a.status, a.finalizada_em = "rascunho", None
    a.trava_usuario_id = a.trava_nome = a.trava_ate = None
    if a.script_versao_id is None and (v := script.ativo(db)):
        a.script_versao_id = v.id  # registro rápido reaberto: agora dá para avaliar o script
    _evento(db, a, usuario, "reaberta", {"motivo": motivo.strip()[:1000], "antes": antes})
    db.flush()
    _pegar_trava(db, a, usuario)
    _aplicar_na_ligacao(db, db.get(Call, a.call_id), a)
    return a


def liberar_trava(db: Session, a: Avaliacao, usuario: Usuario | None, forcar: bool = False) -> None:
    if trava_ativa(a) and not e_minha(a, usuario) and not forcar:
        raise Conflito(f"A avaliação está com {a.trava_nome}. Só um administrador pode liberar.")
    if forcar and not e_minha(a, usuario):
        _evento(db, a, usuario, "trava_liberada", {"estava_com": a.trava_nome})
    a.trava_usuario_id = a.trava_nome = a.trava_ate = None
    db.flush()


def serializar_completa(db: Session, a: Avaliacao, usuario: Usuario | None) -> dict:
    from . import script

    v = db.get(ScriptVersao, a.script_versao_id) if a.script_versao_id else None
    itens = db.scalars(select(AvaliacaoItem).where(AvaliacaoItem.avaliacao_id == a.id)).all()
    marcas = db.scalars(select(AvaliacaoMarca).where(AvaliacaoMarca.avaliacao_id == a.id)
                        .order_by(AvaliacaoMarca.segundos)).all()
    eventos = db.scalars(select(AvaliacaoEvento).where(AvaliacaoEvento.avaliacao_id == a.id)
                         .order_by(AvaliacaoEvento.em, AvaliacaoEvento.id)).all()
    d = serializar(a) or {}
    d.update({
        "call_id": a.call_id,
        "script": script.serializar(db, v) if v else None,
        "itens": [{"item_id": i.item_id, "estado": i.estado, "comentario": i.comentario} for i in itens],
        "marcas": [{"id": m.id, "item_id": m.item_id, "segundos": m.segundos, "tipo": m.tipo, "texto": m.texto}
                   for m in marcas],
        "eventos": [{"em": e.em.isoformat(), "usuario": e.usuario_nome, "acao": e.acao, "detalhe": e.detalhe}
                    for e in eventos],
        "calculo": calcular(db, a) if v else None,
        "trava": {"nome": a.trava_nome, "ate": a.trava_ate.isoformat() if a.trava_ate else None,
                  "ativa": trava_ativa(a), "minha": trava_ativa(a) and e_minha(a, usuario)},
        "desfechos": DESFECHOS,
    })
    return d


def serializar(a: Avaliacao | None) -> dict | None:
    if a is None:
        return None
    iso = lambda d: d.isoformat() if d else None  # noqa: E731
    return {"id": a.id, "status": a.status, "origem": a.origem, "monitora_id": a.monitora_id,
            "monitora_nome": a.monitora_nome, "categoria": a.categoria, "subcategoria": a.subcategoria,
            "pediu_nao_ligar": bool(a.pediu_nao_ligar), "nao_avaliavel_motivo": a.nao_avaliavel_motivo,
            "iniciada_em": iso(a.iniciada_em), "finalizada_em": iso(a.finalizada_em),
            "script_versao_id": a.script_versao_id, "desfecho": a.desfecho, "nota": a.nota,
            "falha_critica": bool(a.falha_critica), "observacao": a.observacao, "feedback_fortes": a.feedback_fortes,
            "feedback_melhorar": a.feedback_melhorar}
