"""Medir a IA: revisão humana como gabarito, acurácia, matriz de confusão e calibração da confiança.

- A revisão humana (pela tela ou a escuta manual importada) vira o resultado da ligação, mas a
  resposta original da IA fica guardada em `categoria_ia` para comparação.
- Uma amostra aleatória das ligações (AMOSTRA_QUALIDADE_PCT) entra na fila de revisão mesmo sem
  dúvida. Sem ela, só os casos difíceis seriam revisados e a medição ficaria enviesada.
"""
import hashlib
import random
from datetime import timedelta

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Call, Tabulacao, agora
from ..taxonomy import CATEGORIES, label_cat, label_sub
from . import custos, tabulacoes

MOTORES_IA = ("openai", "heuristica", "local")  # quem produz a resposta "da IA" que medimos
MOTORES_ESCUTA = ("csv", "html")  # resultado importado de escuta manual (humano)


def na_amostra(call: Call) -> bool:
    """Sorteio determinístico pela ligação: a mesma ligação sempre cai (ou não) na amostra."""
    pct = settings.amostra_qualidade_pct
    if pct <= 0:
        return False
    chave = str(call.id_ligacao or call.id or "")
    n = int(hashlib.sha1(chave.encode()).hexdigest()[:8], 16) % 10000
    return n < pct * 100


def cond_fila():
    """Fila de revisão humana: casos duvidosos + amostra aleatória ainda não revisada."""
    return or_(Call.precisa_revisao.is_(True), and_(Call.na_amostra.is_(True), Call.revisado_em.is_(None)))


def motivo_fila(c: Call) -> str | None:
    if c.precisa_revisao:
        return c.revisao_motivo
    if c.na_amostra and c.revisado_em is None:
        return (f"Amostra aleatória de qualidade ({settings.amostra_qualidade_pct:g}% das ligações): "
                "confira se a IA acertou.")
    return None


def revisar(db: Session, call: Call, categoria: str, subcategoria: str | None, revisor: str,
            observacao: str | None) -> None:
    """Registra a revisão humana: passa a ser o resultado da ligação; a resposta da IA fica guardada."""
    from . import pipeline

    if call.categoria_ia is None and call.motor in MOTORES_IA:
        call.categoria_ia, call.subcategoria_ia = call.categoria, call.subcategoria
    call.categoria_revisada, call.subcategoria_revisada = categoria, subcategoria
    call.categoria, call.subcategoria = categoria, subcategoria
    call.revisado_por, call.revisado_em = revisor.strip()[:80], agora()
    call.revisao_observacao = (observacao or "").strip()[:1000] or None
    pipeline.atualizar_divergencia(db, call)


def desfazer(db: Session, call: Call) -> None:
    """Volta ao resultado da IA (só para ligações que têm resposta da IA)."""
    from . import pipeline

    call.categoria, call.subcategoria = call.categoria_ia, call.subcategoria_ia
    call.categoria_revisada = call.subcategoria_revisada = None
    call.revisado_por = call.revisado_em = call.revisao_observacao = None
    pipeline.atualizar_divergencia(db, call)


# --------------------------------------------------------------------------- medição
FAIXAS = (("abaixo de 60%", 0, 0.6), ("60% a 80%", 0.6, 0.8), ("80% ou mais", 0.8, 1.01))


def _pct(a: int, b: int) -> float:
    return round(100 * a / b, 1) if b else 0.0


def medir(db: Session, ids: set[int] | None = None, desde=None) -> dict:
    """Compara a resposta da IA com a revisão humana nas ligações que têm as duas."""
    from . import pipeline

    q = select(Call).where(Call.revisado_em.is_not(None), Call.categoria_ia.is_not(None),
                           Call.categoria_revisada.is_not(None))
    if ids is not None:
        q = q.where(Call.id.in_(ids))
    if desde is not None:
        q = q.where(Call.revisado_em >= desde)
    calls = db.scalars(q.order_by(Call.revisado_em.desc())).all()

    cats = list(CATEGORIES)
    n = acertos = sub_n = sub_ok = 0
    humano = {c: 0 for c in cats}
    previsto = {c: 0 for c in cats}
    certo = {c: 0 for c in cats}
    conf = {h: {} for h in cats}
    faixas = {f[0]: [0, 0] for f in FAIXAS}
    motores: dict[str, list[int]] = {}
    discord = []

    regras = {r.id: tabulacoes.regra_de(r) for r in db.scalars(select(Tabulacao))}
    nl_ativo = any(r.nao_ligar for r in regras.values())
    apontadas = confirmadas = perdidas = 0

    for c in calls:
        h, ia = c.categoria_revisada, c.categoria_ia
        ok = h == ia
        n += 1
        acertos += ok
        humano[h] = humano.get(h, 0) + 1
        previsto[ia] = previsto.get(ia, 0) + 1
        certo[h] = certo.get(h, 0) + ok
        conf.setdefault(h, {})[ia] = conf.setdefault(h, {}).get(ia, 0) + 1
        if ok and c.subcategoria_revisada:
            sub_n += 1
            sub_ok += c.subcategoria_revisada == c.subcategoria_ia
        if c.confianca is not None:
            for nome, a, b in FAIXAS:
                if a <= c.confianca < b:
                    faixas[nome][0] += 1
                    faixas[nome][1] += ok
        m = motores.setdefault(c.motor or "?", [0, 0])
        m[0] += 1
        m[1] += ok
        if not ok and len(discord) < 25:
            discord.append({
                "id": c.id, "id_ligacao": c.id_ligacao, "data_ligacao": c.data_ligacao.isoformat() if c.data_ligacao else None,
                "operador_nome": c.operador_nome, "humano": h, "humano_label": label_cat(h),
                "humano_sub_label": label_sub(h, c.subcategoria_revisada) if c.subcategoria_revisada else None,
                "ia": ia, "ia_label": label_cat(ia), "ia_sub_label": label_sub(ia, c.subcategoria_ia) if c.subcategoria_ia else None,
                "confianca": c.confianca, "revisado_por": c.revisado_por, "observacao": c.revisao_observacao,
            })

        # As divergências que a IA APONTOU (com as mesmas regras de confiança) se confirmaram na revisão?
        if c.tabulacao_operador or c.tabulacao_id:
            regra = regras.get(c.tabulacao_id) or tabulacoes.sugerir(c.tabulacao_operador)
            div_ia = (ia != "INDETERMINADO" and (c.confianca is None or c.confianca >= settings.confianca_minima_divergencia)
                      and pipeline.comparar(regra, ia, c.subcategoria_ia, c.pediu_nao_ligar, nl_ativo)[0])
            div_h = h != "INDETERMINADO" and pipeline.comparar(regra, h, c.subcategoria_revisada, c.pediu_nao_ligar, nl_ativo)[0]
            apontadas += div_ia
            confirmadas += div_ia and div_h
            perdidas += div_h and not div_ia

    por_cat = []
    for code in cats:
        if humano.get(code) or previsto.get(code):
            por_cat.append({"codigo": code, "label": label_cat(code), "humano": humano.get(code, 0),
                            "ia": previsto.get(code, 0), "acertos": certo.get(code, 0),
                            "precisao": _pct(certo.get(code, 0), previsto.get(code, 0)),
                            "recall": _pct(certo.get(code, 0), humano.get(code, 0))})
    usadas = [c for c in cats if humano.get(c) or previsto.get(c)]

    fila = db.scalar(select(func.count(Call.id)).where(Call.status == "done", cond_fila())) or 0
    revisadas_7d = db.scalar(select(func.count(Call.id)).where(Call.revisado_em >= agora() - timedelta(days=7))) or 0
    escuta = db.scalar(select(func.count(Call.id)).where(Call.revisado_em.is_not(None), Call.categoria_ia.is_(None))) or 0
    return {
        "avaliadas": n,
        "acertos": acertos,
        "acuracia": _pct(acertos, n),
        "acuracia_subcategoria": _pct(sub_ok, sub_n),
        "amostra_pequena": n < 50,
        "por_categoria": por_cat,
        "confusao": {"categorias": usadas,
                     "linhas": [{"humano": h, "total": humano.get(h, 0), "ia": conf.get(h, {})} for h in usadas if humano.get(h)]},
        "por_confianca": [{"faixa": nome, "n": v[0], "acertos": v[1], "acuracia": _pct(v[1], v[0])} for nome, v in faixas.items()],
        "por_motor": [{"motor": k, "n": v[0], "acuracia": _pct(v[1], v[0])} for k, v in sorted(motores.items(), key=lambda x: -x[1][0])],
        "divergencias": {"apontadas": apontadas, "confirmadas": confirmadas, "precisao": _pct(confirmadas, apontadas),
                         "perdidas": perdidas},
        "fila": {"pendentes": fila, "revisadas_7d": revisadas_7d, "amostra_pct": settings.amostra_qualidade_pct,
                 "confianca_minima": settings.confianca_minima_divergencia},
        "gabarito": {"revisadas_sem_resposta_ia": escuta},
        "discordancias": discord,
    }


def candidatos_gabarito(db: Session, n: int, seed: int = 7) -> list[Call]:
    """Ligações revisadas por humano (ex.: escuta manual) que ainda não têm resposta da IA para comparar."""
    calls = db.scalars(select(Call).where(Call.revisado_em.is_not(None), Call.categoria_ia.is_(None),
                                          or_(Call.caminho_audio.is_not(None), Call.transcricao.is_not(None)))).all()
    return random.Random(seed).sample(calls, n) if len(calls) > n else list(calls)


def custo_estimado(calls: list[Call]) -> float:
    total = 0.0
    for c in calls:
        if not c.transcricao:
            total += custos.calcular("transcricao", settings.openai_whisper_model, audio_segundos=c.duracao_segundos or 60)
        total += custos.calcular("classificacao", settings.openai_model, tokens_entrada=1300, tokens_saida=110)
    return round(total, 4)
