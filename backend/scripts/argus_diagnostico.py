"""Confere a conexão com a API do Argus e mostra o FORMATO das respostas (nomes de campo e tipos, sem dados
pessoais). Use para validar o token e conferir os campos dos relatórios de ponto.

Uso (a partir de backend/, com ARGUS_TOKEN no .env):
    python -m scripts.argus_diagnostico
"""
from datetime import datetime, timedelta

from app.services import argus_client, argus_operacao


def _formato(itens: list[dict]) -> str:
    if not itens:
        return "    (nenhum registro)"
    campos = sorted(itens[0].keys())
    return "\n".join(f"    {k}: {type(itens[0][k]).__name__}" for k in campos)


def main() -> None:
    hoje = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    ontem = hoje - timedelta(days=1)
    passos = [
        ("Campanhas (/cmd/listarcampanhas)", lambda: argus_client.listar_campanhas()),
        ("Grupos (/cmd/listargrupos)", lambda: argus_client.listar_grupos()),
        ("Operadores (/cmd/listarusuarios)", lambda: argus_client.listar_usuarios()),
        ("Entrada/saída de ontem (/report/entradasaida)",
         lambda: list(argus_client.entradas_saidas(ontem, hoje - timedelta(seconds=1)))),
        ("Pausas de ontem (/report/pausasdetalhadas)",
         lambda: list(argus_client.pausas_detalhadas(ontem, hoje - timedelta(seconds=1)))),
    ]
    for titulo, fn in passos:
        try:
            itens = fn()
            print(f"OK  {titulo}: {len(itens)} registro(s)\n{_formato(itens)}")
            if "campanhas" in titulo.lower():
                print("    ids: " + ", ".join(f"{c.get('idCampanha')} ({c.get('campanhaDesc')})" for c in itens))
            if "entrada" in titulo.lower() and itens:
                argus_operacao.tabela_ponto(itens, ontem.date())
                print("    → o Crivo reconhece este formato")
            if "pausas" in titulo.lower() and itens:
                argus_operacao.tabela_pausas(itens)
                print("    → o Crivo reconhece este formato")
        except Exception as e:  # noqa: BLE001
            print(f"ERRO {titulo}: {e}")


if __name__ == "__main__":
    main()
