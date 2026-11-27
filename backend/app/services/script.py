"""Script de vendas versionado: seed (transcrição do PDF), leitura, edição de rascunho e publicação.

A avaliação guarda a versão do script com que foi feita: editar o script cria uma versão nova e não
muda avaliações antigas. Só uma versão fica ativa; versão já usada em avaliação não pode ser editada.
"""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Avaliacao, ScriptItem, ScriptSecao, ScriptVersao, agora

APLICABILIDADES = {"sempre": "Sempre", "venda": "Só se houve venda", "recusa": "Só se houve recusa"}

# Transcrição do PDF "2 SCRIPT PARA LEITURA DURANTE" (BenConsig). Os campos entre colchetes são variáveis.
# (texto, orientacao, critico)
SEED: list[dict] = [
    {"titulo": "Abertura", "aplicabilidade": "sempre", "itens": [
        ("“FULANO (nome do cliente), meu nome é (seu nome), sou da BenConsig, tudo bem com o senhor(a)?”", None, False),
        ("“Que maravilha! Que permaneça assim!”", None, False),
    ]},
    {"titulo": "Apresentação da empresa", "aplicabilidade": "sempre", "itens": [
        ("“O senhor(a) conhece a BenConsig?”", None, False),
        ("“Nós somos a maior financeira no ramo de crédito consignado do país, e é por isso que estou te ligando.”", None, False),
        ("“Mas pode ficar tranquilo(a), eu não vim falar sobre empréstimo hoje.”", None, False),
    ]},
    {"titulo": "Contexto do benefício", "aplicabilidade": "sempre", "itens": [
        ("“Eu fiz um levantamento referente ao seu benefício do INSS e identifiquei algumas irregularidades.”", None, False),
        ("“Com isso, surgiu uma oportunidade pra ajudar o senhor(a) com suas dívidas de empréstimo consignado.”", None, False),
    ]},
    {"titulo": "Portabilidade", "aplicabilidade": "sempre", "itens": [
        ("“Agora vamos falar um pouco sobre como eu vou conseguir te ajudar com isso. O senhor(a) já ouviu falar em portabilidade?”", None, False),
        ("“A portabilidade é como quando a gente passa o número de celular da Oi pra Tim.”", None, False),
        ("“Só que aqui a gente passa a dívida de um banco pra outro com juros muito menores.”", None, False),
        ("“E o melhor: o senhor(a) recebe em dinheiro a restituição dos juros abusivos que o banco anterior está cobrando.”", None, False),
    ]},
    {"titulo": "Proposta", "aplicabilidade": "sempre", "itens": [
        ("“Hoje, o senhor(a) está pagando um contrato no banco [X], com uma taxa de juros bem alta, de aproximadamente [X]%.”", None, False),
        ("“Com a portabilidade, essa taxa cai pra 1,67%, e o senhor(a) vai receber R$ [valor] de restituição.”", None, False),
        ("“Importante: a parcela que o senhor(a) paga hoje continua exatamente igual, nada vai mudar no valor descontado do seu benefício.”", None, False),
    ]},
    {"titulo": "Confirmação da conta", "aplicabilidade": "sempre", "itens": [
        ("“FULANO, no meu sistema consta que o senhor(a) recebe o benefício pela conta [nome do banco].”", None, False),
        ("“O senhor(a) quer receber a restituição nessa conta mesmo, ou tem preferência por alguma outra?”", None, False),
    ]},
    {"titulo": "Processo de efetivação da venda", "aplicabilidade": "venda", "itens": [
        ("Coleta do documento oficial: RG ou CNH (frente e verso).", None, True),
        ("Coleta do print de anuência.", None, True),
        ("Texto de confirmação correto.", "De acordo com: banco portado; novo banco; valores e condições da proposta.", True),
    ]},
    {"titulo": "Entenda o motivo da recusa", "aplicabilidade": "recusa", "itens": [
        ("Antes de desistir, entendeu exatamente o que está impedindo o cliente de seguir, com a pergunta: "
         "“O que te impede de fechar esse negócio hoje?”", None, False),
        ("Se o motivo for tratável (insegurança, falta de compreensão, receio com digital etc.): tratou e converteu.", None, False),
        ("Se não for tratável (bloqueio de margem, resistência absoluta ou desinteresse total): agradeceu, enviou a "
         "proposta com os dados completos no WhatsApp e foi para o próximo cliente.", None, False),
    ]},
    {"titulo": "Crie necessidade no cliente", "aplicabilidade": "recusa", "itens": [
        ("Usou a abordagem emocional, voltada para o benefício imediato: “Se hoje o senhor(a) tivesse R$ [valor da "
         "restituição] disponível na conta, qual seria a primeira coisa que faria com esse dinheiro?”",
         "Objetivo: o cliente visualiza o benefício e reconhece que está abrindo mão de algo real e útil.", False),
    ]},
]


def seed_se_vazio(db: Session) -> ScriptVersao | None:
    """Cria a versão 1 (ativa) a partir da transcrição do PDF, se ainda não há nenhum script."""
    if db.scalar(select(func.count(ScriptVersao.id))):
        return None
    v = ScriptVersao(nome="Script BenConsig (PDF “Script para leitura durante”)", numero=1, status="ativa",
                     criado_por="Sistema", publicada_em=agora())
    db.add(v)
    db.flush()
    _gravar_estrutura(db, v, [{"titulo": s["titulo"], "aplicabilidade": s["aplicabilidade"],
                               "itens": [{"texto": t, "orientacao": o, "critico": c} for t, o, c in s["itens"]]}
                              for s in SEED])
    return v


def ativo(db: Session) -> ScriptVersao | None:
    return db.scalars(select(ScriptVersao).where(ScriptVersao.status == "ativa")
                      .order_by(ScriptVersao.numero.desc())).first()


def secoes_e_itens(db: Session, versao_id: int) -> list[tuple[ScriptSecao, list[ScriptItem]]]:
    secoes = db.scalars(select(ScriptSecao).where(ScriptSecao.versao_id == versao_id)
                        .order_by(ScriptSecao.ordem, ScriptSecao.id)).all()
    ids = [s.id for s in secoes]
    itens = db.scalars(select(ScriptItem).where(ScriptItem.secao_id.in_(ids or [-1]))
                       .order_by(ScriptItem.ordem, ScriptItem.id)).all()
    por = {sid: [] for sid in ids}
    for i in itens:
        por[i.secao_id].append(i)
    return [(s, por[s.id]) for s in secoes]


def em_uso(db: Session, versao_id: int) -> int:
    return db.scalar(select(func.count(Avaliacao.id)).where(Avaliacao.script_versao_id == versao_id)) or 0


def serializar(db: Session, v: ScriptVersao) -> dict:
    return {
        "id": v.id, "nome": v.nome, "numero": v.numero, "status": v.status,
        "valor_divergencia": v.valor_divergencia, "criado_em": v.criado_em.isoformat() if v.criado_em else None,
        "criado_por": v.criado_por, "publicada_em": v.publicada_em.isoformat() if v.publicada_em else None,
        "avaliacoes": em_uso(db, v.id),
        "secoes": [{
            "id": s.id, "ordem": s.ordem, "titulo": s.titulo, "aplicabilidade": s.aplicabilidade,
            "aplicabilidade_label": APLICABILIDADES.get(s.aplicabilidade, s.aplicabilidade), "orientacao": s.orientacao,
            "itens": [{"id": i.id, "ordem": i.ordem, "texto": i.texto, "orientacao": i.orientacao, "peso": i.peso,
                       "critico": bool(i.critico)} for i in itens],
        } for s, itens in secoes_e_itens(db, v.id)],
    }


def _gravar_estrutura(db: Session, v: ScriptVersao, secoes: list[dict]) -> None:
    for si, s in enumerate(secoes):
        sec = ScriptSecao(versao_id=v.id, ordem=si, titulo=s["titulo"].strip()[:160],
                          aplicabilidade=s.get("aplicabilidade") or "sempre", orientacao=s.get("orientacao"))
        db.add(sec)
        db.flush()
        for ii, it in enumerate(s.get("itens") or []):
            db.add(ScriptItem(secao_id=sec.id, ordem=ii, texto=it["texto"].strip(), orientacao=it.get("orientacao"),
                              peso=float(it.get("peso") or 1.0), critico=bool(it.get("critico"))))
    db.flush()


def novo_rascunho(db: Session, base: ScriptVersao | None, autor: str | None) -> ScriptVersao:
    """Nova versão em rascunho, copiando a estrutura da versão base (normalmente a ativa)."""
    numero = (db.scalar(select(func.max(ScriptVersao.numero))) or 0) + 1
    v = ScriptVersao(nome=base.nome if base else "Novo script", numero=numero, status="rascunho",
                     valor_divergencia=base.valor_divergencia if base else 0.5, criado_por=autor)
    db.add(v)
    db.flush()
    if base:
        estrutura = serializar(db, base)["secoes"]
        _gravar_estrutura(db, v, estrutura)
    return v


def substituir_estrutura(db: Session, v: ScriptVersao, nome: str, valor_divergencia: float, secoes: list[dict]) -> None:
    """Troca a estrutura inteira de um rascunho (o editor manda o script todo de uma vez)."""
    antigas = [s.id for s in db.scalars(select(ScriptSecao).where(ScriptSecao.versao_id == v.id)).all()]
    if antigas:
        db.query(ScriptItem).filter(ScriptItem.secao_id.in_(antigas)).delete(synchronize_session=False)
        db.query(ScriptSecao).filter(ScriptSecao.id.in_(antigas)).delete(synchronize_session=False)
    v.nome, v.valor_divergencia = nome.strip()[:120], valor_divergencia
    _gravar_estrutura(db, v, secoes)


def publicar(db: Session, v: ScriptVersao) -> None:
    for outra in db.scalars(select(ScriptVersao).where(ScriptVersao.status == "ativa", ScriptVersao.id != v.id)).all():
        outra.status = "arquivada"
    v.status, v.publicada_em = "ativa", agora()
