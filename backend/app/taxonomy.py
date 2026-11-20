"""Taxonomia oficial de categorias/subcategorias (fonte única de verdade).

Versão 2: + "Desligou na abertura", "Ligação caiu" e "Já é cliente". O pedido de "não ligar mais"
(LGPD) não é uma categoria: é uma marcação à parte (`pediu_nao_ligar`), porque pode acontecer em
qualquer resultado (o titular sem interesse ou um terceiro que atendeu).
Cada ligação qualificada guarda a versão usada (`taxonomia_versao`).
"""

TAXONOMIA_VERSAO = 2

CATEGORIES: dict[str, dict] = {
    "EM_NEGOCIACAO": {
        "label": "Em Negociação",
        "desc": "Houve negociação com o cliente.",
        "subs": {
            "PROPOSTA_EM_ANDAMENTO": "Proposta apresentada / em andamento",
            "ACEITE_VERBAL": "Fechamento / aceite verbal",
            "AGENDAMENTO_RETORNO": "Agendamento de retorno",
            "MIGRACAO_WHATSAPP": "Migração para WhatsApp",
        },
    },
    "NAO_E_O_CLIENTE": {
        "label": "Não é o Cliente",
        "desc": "A pessoa não se identifica com o nome falado.",
        "subs": {
            "E_O_CLIENTE_HISTORICO": "É o cliente (identificou-se em outras ligações)",
            "ENGANO_DIRETO": "Engano direto",
            "TERCEIRO_FAMILIA": "Outro membro da família / Terceiro",
            "CHIP_NOVO": "Chip novo / Linha trocada",
            "TITULAR_FALECIDO": "Titular falecido",
            "RECLAMACAO_RECORRENTE": "Reclamação de chamadas recorrentes p/ pessoa errada",
        },
    },
    "SEM_INTERESSE": {
        "label": "Cliente Não tem Interesse",
        "desc": "O cliente não quer fechar negócio ou ouvir a proposta.",
        "subs": {
            "CLIENTE_REVOLTADO": "Cliente revoltado",
            "CLIENTE_CALMO": "Cliente calmo",
            "JA_POSSUI": "Já possui / sem margem",
            "JA_E_CLIENTE": "Já é cliente / já contratou com a empresa",
        },
    },
    "LIGACAO_MUDA": {
        "label": "Ligação Muda",
        "desc": "Não houve diálogo efetivo com o cliente (silêncio, um lado só, ou a ligação acabou antes da conversa).",
        "subs": {
            "ATENDENTE_SOLITARIO": "Atendente solitário",
            "CLIENTE_SOLITARIO": "Cliente solitário",
            "FALHA_COMUNICACAO": "Falha de comunicação",
            "MUDO_TOTAL": "Mudo total (silêncio bilateral)",
            "DESLIGOU_NA_ABERTURA": "Desligou logo na abertura",
            "LIGACAO_CAIU": "Ligação caiu / interrompida",
        },
    },
    "CAIXA_POSTAL": {
        "label": "Caixa Postal",
        "desc": "Ligações em que há um não humano falando.",
        "subs": {
            "URA_OPERADORA": "URA da operadora",
            "POS_BIP": "Caixa postal pós-bip / recado",
            "FAX_MODEM": "Fax / modem / tom técnico",
            "NUMERO_INEXISTENTE": "Número inexistente / bloqueado",
        },
    },
    "INDETERMINADO": {
        "label": "Indeterminado",
        "desc": "Não foi possível classificar (áudio ausente/ilegível).",
        "subs": {
            "SEM_DADOS": "Sem dados suficientes",
            "AUDIO_INAUDIVEL": "Áudio inaudível / ininteligível",
        },
    },
}


def label_cat(code: str) -> str:
    return CATEGORIES.get(code, {}).get("label", code)


def label_sub(cat: str, sub: str | None) -> str:
    if not sub:
        return "-"
    return CATEGORIES.get(cat, {}).get("subs", {}).get(sub, sub)


def valid(cat: str, sub: str | None) -> bool:
    return cat in CATEGORIES and (sub is None or sub in CATEGORIES[cat]["subs"])
