"""Apaga os dados da versão anterior do Crivo, com IA, que ficaram ocultos no banco.

Depois da migração para a monitoria humana, transcrições, resumos, confiança, custos e a tabela de uso
da OpenAI (ia_uso) continuam no banco, só não aparecem mais. Este script apaga esses dados de vez.
Não mexe no resultado das ligações nem nas avaliações das monitoras.

Uso (a partir de backend/; faça um backup do banco antes):
    python -m scripts.limpar_dados_ia          # só mostra o que seria apagado
    python -m scripts.limpar_dados_ia --sim    # apaga
"""
import argparse

from sqlalchemy import inspect, text

from app.database import engine

# colunas de IA da tabela calls (a revisão humana já virou avaliação na migração)
COLUNAS_IA = ["confianca", "motor", "resumo", "evidencia", "transcricao", "transcricao_diarizada",
              "metricas_acusticas", "sentimento_cliente", "categoria_ia", "subcategoria_ia", "fala_segundos",
              "custo_usd", "qualificado_em", "precisa_revisao", "revisao_motivo", "na_amostra"]


def levantar() -> dict:
    insp = inspect(engine)
    cols = {c["name"] for c in insp.get_columns("calls")} if insp.has_table("calls") else set()
    presentes = [c for c in COLUNAS_IA if c in cols]
    out = {"colunas": presentes, "ligacoes_com_dados": 0, "ia_uso": None}
    with engine.connect() as conn:
        if presentes:
            cond = " OR ".join(f"{c} IS NOT NULL" for c in presentes)
            out["ligacoes_com_dados"] = conn.execute(text(f"SELECT COUNT(*) FROM calls WHERE {cond}")).scalar()
        if insp.has_table("ia_uso"):
            out["ia_uso"] = conn.execute(text("SELECT COUNT(*) FROM ia_uso")).scalar()
    return out


def limpar() -> dict:
    antes = levantar()
    with engine.begin() as conn:
        if antes["ia_uso"] is not None:
            conn.execute(text("DELETE FROM ia_uso"))
        if antes["colunas"]:
            conn.execute(text(f"UPDATE calls SET {', '.join(f'{c} = NULL' for c in antes['colunas'])}"))
    return antes


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sim", action="store_true", help="confirma: apaga de verdade")
    a = ap.parse_args()
    r = levantar()
    print(f"Ligações com dados de IA: {r['ligacoes_com_dados']} (colunas: {', '.join(r['colunas']) or 'nenhuma'})")
    print(f"Registros de uso da IA: {r['ia_uso'] if r['ia_uso'] is not None else 'tabela inexistente'}")
    if not a.sim:
        print("Nada foi apagado. Para apagar, rode de novo com --sim (faça um backup antes).")
    else:
        limpar()
        print("Dados de IA apagados. Os resultados e as avaliações das monitoras foram mantidos.")
