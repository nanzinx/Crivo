"""Confere a detecção local de fala contra ligações JÁ classificadas. Não usa IA: custo zero.

Pergunta que responde: "se o Crivo tivesse resolvido sozinho as ligações sem fala, teria descartado
como MUDA alguma ligação que na verdade tinha conversa?"

Uso (a partir de backend/):
    python -m scripts.validar_vad            # todas as ligações classificadas com áudio no disco
    python -m scripts.validar_vad --n 500    # amostra

Leia o resultado assim:
  - "Mudas de verdade resolvidas sem IA": a economia (e quanto áudio deixaria de ser transcrito).
  - "ERROS": ligações com conversa que seriam descartadas. O esperado é ZERO. Se houver, não ative
    (VAD_ATIVO=false) ou aumente a sensibilidade baixando VAD_FALA_MINIMA_SEGUNDOS.
"""
import argparse
import random
from collections import Counter
from pathlib import Path

from sqlalchemy import select

from app.config import settings
from app.database import SessionLocal, init_db
from app.models import Call
from app.services import audio_analyzer
from app.taxonomy import label_cat


def avaliar(n: int | None = None, seed: int = 7) -> dict:
    init_db()
    with SessionLocal() as db:
        calls = [c for c in db.scalars(select(Call).where(Call.categoria.is_not(None), Call.motor != "local",
                                                          Call.caminho_audio.is_not(None)))
                 if Path(c.caminho_audio).exists()]
    if n and len(calls) > n:
        calls = random.Random(seed).sample(calls, n)

    total = Counter()
    sem_fala = Counter()
    erros, seg_poupados, sem_vad = [], 0.0, 0
    seg_total = seg_apos_corte = 0.0  # só das ligações com fala (as que iriam para a IA)
    estereo = 0
    for c in calls:
        m = audio_analyzer.analyze(c.caminho_audio)
        if not m.get("vad"):
            sem_vad += 1
            continue
        total[c.categoria] += 1
        if (m.get("fala_segundos") or 0) < settings.vad_fala_minima_segundos:
            sem_fala[c.categoria] += 1
            if c.categoria == "LIGACAO_MUDA":
                seg_poupados += m.get("duracao_segundos") or 0
            elif c.categoria != "INDETERMINADO":
                erros.append((c.id, c.id_ligacao, c.categoria, m.get("fala_segundos"), c.nome_arquivo))
        else:
            seg_total += m.get("duracao_segundos") or 0
            seg_apos_corte += m.get("duracao_apos_corte") or m.get("duracao_segundos") or 0
            estereo += bool(m.get("fala_por_canal"))
    return {"analisadas": sum(total.values()), "sem_vad": sem_vad, "total": total, "sem_fala": sem_fala,
            "erros": erros, "minutos_poupados": seg_poupados / 60, "minutos_com_fala": seg_total / 60,
            "minutos_apos_corte": seg_apos_corte / 60, "estereo_separado": estereo}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n", type=int, default=None, help="tamanho da amostra (padrão: todas)")
    r = avaliar(ap.parse_args().n)
    if not r["analisadas"]:
        print("Nenhuma ligação classificada com áudio no disco. Importe o acervo e o CSV de escuta primeiro.")
        return
    print(f"\nLigações analisadas: {r['analisadas']}  (sem leitura de áudio: {r['sem_vad']})\n")
    print(f"{'Categoria (gabarito)':28s} {'total':>7s} {'sem fala':>9s}")
    for cat, n in r["total"].most_common():
        print(f"{label_cat(cat):28s} {n:7d} {r['sem_fala'][cat]:9d}")
    mudas = r["sem_fala"]["LIGACAO_MUDA"]
    print(f"\nMudas de verdade resolvidas sem IA: {mudas} ({r['minutos_poupados']:.1f} min de áudio não transcritos)")
    print(f"ERROS (tinham conversa e seriam descartadas): {len(r['erros'])}")
    for e in r["erros"][:30]:
        print(f"   ligação #{e[0]} (Argus {e[1]}) gabarito={label_cat(e[2])} fala={e[3]}s  {e[4] or ''}")
    if r["minutos_com_fala"]:
        eco = 1 - r["minutos_apos_corte"] / r["minutos_com_fala"]
        print(f"\nCorte de silêncio (estimativa): {r['minutos_com_fala']:.1f} min -> {r['minutos_apos_corte']:.1f} min "
              f"({eco:.0%} a menos de transcrição)")
        print(f"Gravações em estéreo com os lados separados: {r['estereo_separado']} de {r['analisadas']}"
              + ("" if r["estereo_separado"] else "  (configure ARGUS_AUDIO_CHANNELS=3 para separar operador e cliente)"))
    print("\n=> " + ("Seguro ativar a resolução local." if not r["erros"] else
                    "NÃO ative como está: ouça as ligações acima e ajuste VAD_FALA_MINIMA_SEGUNDOS."))


if __name__ == "__main__":
    main()
