"""Exporta gravações num .zip organizado em pastas: Equipe / Operador / Cliente / Tabulação.

Feito para a monitoria baixar e mandar no BenHub. Junto vai `lista_gravacoes.csv`, com o caminho de cada
arquivo no .zip e os dados da ligação (inclusive as que ficaram de fora por não ter gravação).
"""
import csv
import io
import re
import unicodedata
import zipfile
from pathlib import Path

from ..models import Avaliacao, Call

_PROIBIDOS = re.compile(r'[\\/:*?"<>|\x00-\x1f]+')


def pasta(nome: str | None, padrao: str) -> str:
    """Nome seguro para pasta/arquivo em Windows, Mac e Linux (mantém acentos)."""
    n = unicodedata.normalize("NFC", (nome or "").strip())
    n = _PROIBIDOS.sub(" ", n)
    n = re.sub(r"\s+", " ", n).strip(" .")
    return (n or padrao)[:60].rstrip(" .") or padrao


def caminho(c: Call) -> str:
    quando = c.data_ligacao.strftime("%Y-%m-%d_%H%M%S") if c.data_ligacao else "sem-data"
    ext = Path(c.caminho_audio or "").suffix.lower() or ".mp3"
    return "/".join([
        pasta(c.grupo_origem, "Sem equipe"),
        pasta(c.operador_nome, "Sem operador"),
        pasta(c.cliente_identificado or c.nome_esperado, "Cliente não identificado"),
        pasta(c.tabulacao_operador, "Sem tabulação"),
        f"{quando}_lig{c.id_ligacao or c.id}{ext}",
    ])


def gerar(destino, calls: list[Call], avals: dict[int, Avaliacao]) -> dict:
    """Escreve o .zip em `destino` (arquivo aberto em modo binário). Devolve quantas entraram e quantas não."""
    incluidas, sem_audio = 0, 0
    lista = io.StringIO()
    w = csv.writer(lista, delimiter=";")
    w.writerow(["Arquivo no zip", "ID Ligação", "Data/Hora", "Equipe", "Operador", "Cliente", "Telefone",
                "Tabulação do operador", "Resultado (monitoria)", "Nota do script", "Gravação"])
    usados: set[str] = set()
    # MP3/WAV já são comprimidos o bastante: guarda sem recomprimir (mais rápido)
    with zipfile.ZipFile(destino, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as z:
        for c in calls:
            a = avals.get(c.avaliacao_id) if c.avaliacao_id else None
            arq = caminho(c)
            existe = bool(c.caminho_audio) and Path(c.caminho_audio).is_file()
            if existe:
                n = 2
                base = arq
                while arq in usados:  # mesma ligação não se repete, mas por segurança
                    arq = base.replace(".", f"_{n}.", 1) if "." in base else f"{base}_{n}"
                    n += 1
                usados.add(arq)
                z.write(c.caminho_audio, arq)
                incluidas += 1
            else:
                sem_audio += 1
            w.writerow([arq if existe else "", c.id_ligacao or c.id,
                        c.data_ligacao.strftime("%d/%m/%Y %H:%M:%S") if c.data_ligacao else "", c.grupo_origem or "",
                        c.operador_nome or "", c.cliente_identificado or c.nome_esperado or "", c.telefone or "",
                        c.tabulacao_operador or "", c.categoria or "",
                        f"{a.nota:.1f}".replace(".", ",") if a and a.nota is not None else "",
                        "incluída" if existe else "sem gravação no servidor"])
        z.writestr("lista_gravacoes.csv", "﻿" + lista.getvalue())
    return {"incluidas": incluidas, "sem_audio": sem_audio}
