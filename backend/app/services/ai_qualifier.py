"""Qualificação: OpenAI (ChatGPT + Whisper) ou heurística sobre transcrição."""
import json
import re
import unicodedata
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel

from ..config import settings
from ..taxonomy import CATEGORIES, valid


class Turno(BaseModel):
    speaker: str  # ATENDENTE | CLIENTE | URA
    text: str
    sentiment: Optional[str] = None  # calmo | revoltado | neutro


class Resultado(BaseModel):
    categoria: str
    subcategoria: Optional[str] = None
    confianca: float = 0.5
    resumo: str = ""
    evidencia: str = ""
    transcricao: str = ""
    turnos: List[Turno] = []
    sentimento_cliente: Optional[str] = None
    motor: str = "heuristica"


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFD", s.lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def _has(text: str, words: list[str]) -> str | None:
    for w in words:
        if re.search(w, text):
            return w
    return None


def heuristica(transcricao: str | None, duracao: float | None) -> Resultado:
    t = _norm(transcricao or "")
    words = len(t.split())
    r = lambda c, s, conf, why, **k: Resultado(  # noqa: E731
        categoria=c, subcategoria=s, confianca=conf, resumo=why, evidencia=why,
        transcricao=transcricao or "", motor="heuristica", **k)

    if words == 0:
        return r("LIGACAO_MUDA", "MUDO_TOTAL", 0.6, "Sem fala transcrita.")
    if k := _has(t, [r"caixa postal", r"deixe (seu|sua) (recado|mensagem)", r"apos o sinal", r"apos o bip",
                     r"nao existe", r"fora de area", r"desligado ou", r"nao pode atender"]):
        sub = "NUMERO_INEXISTENTE" if k in ("nao existe",) else "URA_OPERADORA"
        return r("CAIXA_POSTAL", sub, 0.75, f"Termo de máquina/URA: '{k}'.")
    if words <= 6 and (duracao or 0) < 8:
        return r("LIGACAO_MUDA", "ATENDENTE_SOLITARIO", 0.55, "Fala mínima, sem resposta do cliente.")
    if k := _has(t, [r"faleceu", r"morreu", r"falecid", r"obito", r"ja morreu"]):
        return r("NAO_E_O_CLIENTE", "TITULAR_FALECIDO", 0.8, f"Menção a óbito: '{k}'.")
    if k := _has(t, [r"\bchip\b", r"linha nova", r"numero novo", r"comprei (esse|o) numero", r"era de outra pessoa"]):
        return r("NAO_E_O_CLIENTE", "CHIP_NOVO", 0.65, f"Linha trocada: '{k}'.")
    nao_e = _has(t, [r"nao (e|eh) (ela|ele|o|a|da|do)\b", r"nao conhec", r"engano", r"numero errado",
                     r"nao mora", r"nao (e|eh) (esse|essa|aqui)", r"nao pertence", r"desconheco"])
    if nao_e:
        if _has(t, [r"todo dia", r"vezes", r"toda hora", r"o dia inteiro", r"constantemente", r"de novo"]):
            return r("NAO_E_O_CLIENTE", "RECLAMACAO_RECORRENTE", 0.7, "Reclama de ligações repetidas.")
        if _has(t, [r"esposo", r"marido", r"esposa", r"filh[oa]", r"\bmae\b", r"\bpai\b", r"irma[oa]",
                    r"sobrinh", r"\btia\b", r"\btio\b", r"vizinh", r"so chega"]):
            return r("NAO_E_O_CLIENTE", "TERCEIRO_FAMILIA", 0.65, "Terceiro/familiar atendeu.")
        return r("NAO_E_O_CLIENTE", "ENGANO_DIRETO", 0.7, f"Nega ser o titular: '{nao_e}'.")
    if _has(t, [r"nao tenho interesse", r"nao quero", r"nao preciso", r"pare de ligar", r"tira(r)? (meu|esse) numero",
                r"nao me liga", r"sem interesse"]):
        if _has(t, [r"porra", r"caralho", r"merda", r"pelo amor de deus", r"saco", r"inferno", r"droga",
                    r"vai se", r"nao aguento"]):
            return r("SEM_INTERESSE", "CLIENTE_REVOLTADO", 0.7, "Recusa com tom agressivo.",
                     sentimento_cliente="revoltado")
        return r("SEM_INTERESSE", "CLIENTE_CALMO", 0.65, "Recusa educada.", sentimento_cliente="calmo")
    if _has(t, [r"proposta", r"margem", r"parcela", r"taxa", r"whatsapp", r"valor", r"fechar", r"quanto",
                r"simula", r"beneficio", r"emprestimo", r"portabilidade"]) and words > 25:
        return r("EM_NEGOCIACAO", "PROPOSTA_EM_ANDAMENTO", 0.5, "Diálogo sobre proposta/valores.")
    return r("INDETERMINADO", "SEM_DADOS", 0.3, "Sem padrão claro na transcrição.")


_SYSTEM_PROMPT = """Você é um auditor sênior de qualidade e conformidade de ligações de contact center (discadora automática) no Brasil.
Sua função é analisar detalhadamente o diálogo da chamada e qualificá-la rigorosamente na taxonomia abaixo.

Categorias e subcategorias válidas (use exatamente estes códigos):
{tax}

Diretrizes obrigatórias de classificação:
1. 'EM_NEGOCIACAO': Houve diálogo efetivo sobre a proposta/benefício (empréstimo, portabilidade, restituição, valores, parcelas, margem).
   - PROPOSTA_EM_ANDAMENTO: Diálogo em andamento ou proposta explicada.
   - ACEITE_VERBAL: O cliente aceitou ou confirmou dados para formalização.
   - AGENDAMENTO_RETORNO: Titular pediu retorno em outro horário.
   - MIGRACAO_WHATSAPP: Cliente solicitou envio pelo WhatsApp.

2. 'NAO_E_O_CLIENTE': A pessoa que atendeu não se identifica como o nome esperado.
   - ENGANO_DIRETO: Informou que ligaram errado e desconhece o titular.
   - TERCEIRO_FAMILIA: Parente/cônjuge/terceiro atendeu (ex: "é do meu marido", "ela só chega à noite").
   - CHIP_NOVO: Linha adquirida recentemente da operadora.
   - TITULAR_FALECIDO: Informação expressa de óbito do titular procurado.
   - RECLAMACAO_RECORRENTE: Reclama com ênfase de ligações repetidas/inconvenientes para pessoa errada.
   (Nota: 'E_O_CLIENTE_HISTORICO' é validado pelo sistema cruzando o histórico).

3. 'SEM_INTERESSE': O titular confirmado não quer a proposta.
   - CLIENTE_REVOLTADO: Recusa grosseira, palavrões, gritos, agressividade.
   - CLIENTE_CALMO: Recusa educada, cortês ou neutra ("não tenho interesse, obrigado").
   - JA_POSSUI: Explica que já fez empréstimo/portabilidade ou não possui margem.

4. 'LIGACAO_MUDA': Sem diálogo recíproco.
   - ATENDENTE_SOLITARIO: O atendente fala ("alô, bom dia"), mas o outro lado fica mudo ou sem resposta.
   - CLIENTE_SOLITARIO: O cliente fala ("alô? quem fala?"), mas o atendente não responde.
   - FALHA_COMUNICACAO: Ambos tentam falar simultaneamente, mas não se ouvem ("alô? não escuto").
   - MUDO_TOTAL: Silêncio bilateral absoluto, sem falas inteligíveis.

5. 'CAIXA_POSTAL': Atendimento por voz não humana.
   - URA_OPERADORA: Mensagem gravada da operadora ("deixe seu recado", "número indisponível").
   - POS_BIP: Gravação após o bip de correio de voz.
   - FAX_MODEM: Sinal técnico de modem/fax.
   - NUMERO_INEXISTENTE: Mensagem de número inexistente ou bloqueado.

Instruções de saída:
- `categoria`: Código exato da categoria.
- `subcategoria`: Código exato da subcategoria.
- `confianca`: Valor entre 0.0 e 1.0.
- `resumo`: Breve explicação de 1 a 2 frases fundamentando a escolha.
- `evidencia`: Citação textual literal exata do trecho da fala que comprova a decisão.
- `turnos`: Lista de falas diarizadas com `speaker` ('ATENDENTE', 'CLIENTE' ou 'URA'), `text` e `sentiment` ('calmo', 'revoltado' ou 'neutro').
- `sentimento_cliente`: Sentimento geral ('calmo', 'revoltado', 'neutro' ou nulo se mudo/ura).
"""


def _tax_text() -> str:
    return "\n".join(f"- {c}: {', '.join(v['subs'])}" for c, v in CATEGORIES.items() if c != "INDETERMINADO")


def transcrever_audio(client, audio_path: str) -> str:
    with open(audio_path, "rb") as f:
        tr = client.audio.transcriptions.create(
            model=settings.openai_whisper_model,
            file=f,
            language="pt",
        )
    return getattr(tr, "text", "") or ""


def classificar_openai(audio_path: str | None, nome: str | None, tel: str | None, dur: float | None, transcricao: str | None = None) -> Resultado:
    from openai import OpenAI

    client = OpenAI(api_key=settings.openai_api_key)
    texto = transcricao
    if not texto and audio_path and Path(audio_path).exists():
        texto = transcrever_audio(client, audio_path)

    texto = texto or ""
    system_prompt = _SYSTEM_PROMPT.format(tax=_tax_text())
    user_prompt = (
        f"Metadados da ligação:\n"
        f"- Nome esperado do titular: {nome or '(não informado)'}\n"
        f"- Telefone: {tel or '(não informado)'}\n"
        f"- Duração: {dur or '?'} segundos\n\n"
        f"Transcrição da chamada:\n\"\"\"\n{texto}\n\"\"\""
    )

    resp = client.beta.chat.completions.parse(
        model=settings.openai_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        response_format=Resultado,
    )
    res = resp.choices[0].message.parsed
    if not res:
        return heuristica(texto, dur)
    res.motor = "openai"
    if not res.transcricao:
        res.transcricao = texto
    if not valid(res.categoria, res.subcategoria):
        res.categoria, res.subcategoria = "INDETERMINADO", "SEM_DADOS"
    return res


def qualificar(audio_path: str | None, nome, tel, dur, transcricao: str | None = None) -> Resultado:
    if settings.openai_api_key:
        try:
            return classificar_openai(audio_path, nome, tel, dur, transcricao)
        except Exception as e:  # cai para heurística
            res = heuristica(transcricao, dur)
            res.resumo += f" (OpenAI falhou: {str(e)[:120]})"
            return res
    return heuristica(transcricao, dur)
