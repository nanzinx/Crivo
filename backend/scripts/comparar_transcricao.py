"""Compara modelos de transcrição pelo que importa: a CATEGORIA final bate com a dos auditores?

ATENÇÃO: este script chama a IA e CUSTA DINHEIRO (transcreve cada ligação uma vez por modelo).
Com --n 50 e dois modelos, espere algo na casa de US$ 1. Nada é gravado no banco.

Usa como gabarito as ligações importadas do CSV/HTML de escuta manual (motor "csv" ou "html")
que tenham o áudio no disco.

Uso (a partir de backend/, com OPENAI_API_KEY no .env):
    python -m scripts.comparar_transcricao --n 50 --modelos whisper-1,gpt-4o-mini-transcribe

Para testar o TRATAMENTO do áudio (corte de silêncio e um lado por canal no estéreo), acrescente
"+tratado" ao modelo. Sem o sufixo, o arquivo original é enviado inteiro:
    python -m scripts.comparar_transcricao --n 50 --modelos gpt-4o-mini-transcribe,gpt-4o-mini-transcribe+tratado
Só mantenha CORTAR_SILENCIO / TRANSCRICAO_POR_CANAL ligados se o acerto ficar igual ou melhor.
"""
import argparse
import random
from pathlib import Path

from sqlalchemy import select

from app.config import settings
from app.database import SessionLocal, init_db
from app.models import Call
from app.services import ai_qualifier, audio_analyzer, custos
from app.taxonomy import label_cat


def amostra(n: int, seed: int = 7) -> list[Call]:
    init_db()
    with SessionLocal() as db:
        calls = [c for c in db.scalars(select(Call).where(Call.motor.in_(("csv", "html")), Call.categoria.is_not(None),
                                                          Call.caminho_audio.is_not(None)))
                 if Path(c.caminho_audio).exists()]
    return random.Random(seed).sample(calls, n) if len(calls) > n else calls


def avaliar(calls: list[Call], modelos: list[str]) -> dict[str, dict]:
    client = ai_qualifier._cliente_openai()
    out = {}
    for variante in modelos:
        modelo, tratado = variante.removesuffix("+tratado"), variante.endswith("+tratado")
        acertos = falhas = 0
        custo = minutos = 0.0
        erros = []
        for c in calls:
            dur = c.duracao_segundos or audio_analyzer.analyze(c.caminho_audio).get("duracao_segundos") or 0
            try:
                if tratado:
                    texto, uso, _ = ai_qualifier._transcrever(client, c.caminho_audio, dur, modelo)
                    enviados = sum(u["audio_segundos"] for u in uso)
                else:
                    texto, enviados = ai_qualifier.transcrever_audio(client, c.caminho_audio, modelo), dur
                minutos += enviados / 60
                custo += custos.calcular("transcricao", modelo, audio_segundos=enviados)
                res, tin, tout = ai_qualifier._classificar_texto(client, texto, c.nome_esperado, c.telefone, dur)
                custo += custos.calcular("classificacao", settings.openai_model, tokens_entrada=tin, tokens_saida=tout)
            except Exception as e:
                falhas += 1
                erros.append((c.id, "falha", str(e)[:80]))
                continue
            if res and res.categoria == c.categoria:
                acertos += 1
            else:
                erros.append((c.id, label_cat(c.categoria), label_cat(res.categoria) if res else "—"))
        n = len(calls)
        out[variante] = {"n": n, "acertos": acertos, "falhas": falhas, "acuracia": acertos / n if n else 0,
                       "minutos": minutos, "custo_usd": custo, "custo_por_ligacao": custo / n if n else 0, "erros": erros}
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--modelos", default="whisper-1,gpt-4o-mini-transcribe")
    a = ap.parse_args()
    if not settings.openai_api_key:
        raise SystemExit("Defina OPENAI_API_KEY no .env.")
    calls = amostra(a.n)
    if not calls:
        raise SystemExit("Sem gabarito: importe o CSV de escuta e as gravações (Saúde do sistema > Importar acervo local).")
    r = avaliar(calls, [m.strip() for m in a.modelos.split(",") if m.strip()])
    print(f"\n{len(calls)} ligações do gabarito (escuta manual)\n")
    print(f"{'Transcrição':36s} {'acerto':>8s} {'falhas':>7s} {'minutos':>8s} {'custo':>10s} {'por ligação':>12s}")
    for m, x in r.items():
        print(f"{m:36s} {x['acuracia']:8.1%} {x['falhas']:7d} {x['minutos']:8.1f} {x['custo_usd']:9.3f}$ {x['custo_por_ligacao']:11.5f}$")
    for m, x in r.items():
        print(f"\nDiscordâncias com {m} (ligação, auditor, IA):")
        for e in x["erros"][:15]:
            print(f"   #{e[0]}: {e[1]}  ->  {e[2]}")
    print("\n=> Adote um modelo mais barato ou o tratamento do áudio só se o acerto ficar igual ou melhor.")


if __name__ == "__main__":
    main()
