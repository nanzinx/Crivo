"""Taxonomia oficial de categorias/subcategorias (fonte única de verdade)."""

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
        },
    },
    "LIGACAO_MUDA": {
        "label": "Ligação Muda",
        "desc": "A gravação não apresenta o áudio do cliente.",
        "subs": {
            "ATENDENTE_SOLITARIO": "Atendente solitário",
            "CLIENTE_SOLITARIO": "Cliente solitário",
            "FALHA_COMUNICACAO": "Falha de comunicação",
            "MUDO_TOTAL": "Mudo total (silêncio bilateral)",
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
