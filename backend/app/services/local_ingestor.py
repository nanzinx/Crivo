"""Importa gravações locais (padrão Argus no nome do arquivo) e o CSV legado."""
import csv
import io
import re
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Call

FILE_RE = re.compile(
    r"^(?P<data>\d{4}-\d{2}-\d{2})_(?P<hora>\d{6})_nr(?P<nr>\d+)_id(?P<id>\d+)_(?P<tel>\d+)_(?P<nome>.*)\.(?:mp3|wav)$",
    re.I,
)

LEGACY_CAT = {
    "CLIENTE_NAO_SE_IDENTIFICA": "NAO_E_O_CLIENTE",
    "NINGUEM_FALA_NADA": "LIGACAO_MUDA",
    "CLIENTE_NAO_FALA_NADA": "LIGACAO_MUDA",
    "CAIXA_POSTAL": "CAIXA_POSTAL",
}


def legacy_sub(cat: str, sub: str) -> str | None:
    s = (sub or "").lower()
    if cat == "NINGUEM_FALA_NADA":
        return "MUDO_TOTAL"
    if cat == "CLIENTE_NAO_FALA_NADA":
        return "ATENDENTE_SOLITARIO"
    if cat == "CAIXA_POSTAL":
        return "URA_OPERADORA"
    if "falecido" in s:
        return "TITULAR_FALECIDO"
    if "chip" in s or "linha" in s:
        return "CHIP_NOVO"
    if "família" in s or "familia" in s or "terceiro" in s:
        return "TERCEIRO_FAMILIA"
    if "recorrente" in s:
        return "RECLAMACAO_RECORRENTE"
    return "ENGANO_DIRETO"


def parse_filename(name: str) -> dict | None:
    m = FILE_RE.match(name)
    if not m:
        return None
    dt = datetime.strptime(m["data"] + m["hora"], "%Y-%m-%d%H%M%S")
    return {"data_ligacao": dt, "nr_lead": int(m["nr"]), "id_ligacao": int(m["id"]),
            "telefone": m["tel"], "nome_esperado": m["nome"].strip() or None}


def import_folder(db: Session, folder: str | None = None, limit: int | None = None) -> dict:
    folder_p = Path(folder or settings.recordings_dir)
    existing = set(db.scalars(select(Call.nome_arquivo)).all())
    new = skipped = 0
    for f in sorted(folder_p.glob("*.*")):
        if f.suffix.lower() not in (".mp3", ".wav") or f.name in existing:
            skipped += 1
            continue
        meta = parse_filename(f.name)
        if not meta:
            skipped += 1
            continue
        db.add(Call(nome_arquivo=f.name, caminho_audio=str(f), origem="local", status="pending", **meta))
        new += 1
        if limit and new >= limit:
            break
    db.commit()
    return {"novas": new, "ignoradas": skipped}



def _nk(s: str) -> str:
    import unicodedata

    s = unicodedata.normalize("NFD", (s or "").strip().lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def _label_index() -> tuple[dict, dict]:
    from ..taxonomy import CATEGORIES

    cats = {_nk(v["label"]): k for k, v in CATEGORIES.items()}
    subs = {(k, _nk(lbl)): code for k, v in CATEGORIES.items() for code, lbl in v["subs"].items()}
    return cats, subs


# rótulos do relatório que diferem dos rótulos da taxonomia
_SUB_ALIAS = {
    "houve negociacao com o cliente": "PROPOSTA_EM_ANDAMENTO",
    "chip novo / linha trocada": "CHIP_NOVO",
    "engano direto": "ENGANO_DIRETO",
    "outro membro da familia / terceiro": "TERCEIRO_FAMILIA",
    "titular falecido": "TITULAR_FALECIDO",
    "e o cliente, pois em outras ligacoes ele se identificou como tal": "E_O_CLIENTE_HISTORICO",
    "cliente calmo": "CLIENTE_CALMO",
    "cliente revoltado": "CLIENTE_REVOLTADO",
    "atendente solitario": "ATENDENTE_SOLITARIO",
    "cliente solitario": "CLIENTE_SOLITARIO",
    "falha de comunicacao": "FALHA_COMUNICACAO",
    "caixa postal": None,
}


def import_legacy_csv(db: Session, path: str | None = None) -> dict:
    """Importa o relatório da escuta manual/anterior. Aceita ';' ou ',' e cabeçalhos com/sem acento."""
    p = Path(path or settings.legacy_csv)
    if not p.exists():
        return {"erro": f"CSV não encontrado: {p}"}
    cats, subs = _label_index()
    text = p.read_text(encoding="utf-8-sig", errors="replace")
    delim = ";" if text.split("\n", 1)[0].count(";") >= text.split("\n", 1)[0].count(",") else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delim)
    reader.fieldnames = [_nk(h) for h in reader.fieldnames or []]
    enriched = created = mapped = 0
    for row in reader:
        nome_arq = (row.get("arquivo") or "").strip()
        meta = parse_filename(nome_arq)
        if not meta:
            continue
        call = db.scalars(select(Call).where(Call.nome_arquivo == nome_arq)).first()
        if call is None:
            call = Call(nome_arquivo=nome_arq, origem="csv", status="pending", **meta)
            f = Path(settings.recordings_dir) / nome_arq
            if f.exists():
                call.caminho_audio = str(f)
            db.add(call)
            created += 1
        call.transcricao = call.transcricao or (row.get("transcricao completa") or row.get("transcricao") or None)
        dur = row.get("duracao (segundos)") or row.get("duracao_segundos")
        try:
            call.duracao_segundos = float(str(dur).replace(",", "."))
        except (TypeError, ValueError):
            pass
        cat = cats.get(_nk(row.get("categoria", "")))
        if cat and call.status != "done":
            sub_label = _nk(row.get("subcategoria", ""))
            sub = _SUB_ALIAS.get(sub_label, subs.get((cat, sub_label)))
            call.categoria, call.subcategoria = cat, sub
            call.status, call.motor, call.confianca = "done", "csv", 0.8
            call.resumo = "Importado do relatório de escuta anterior."
            call.conflito_identidade = sub == "E_O_CLIENTE_HISTORICO"
            call.qualificado_em = datetime.utcnow()
            mapped += 1
        enriched += 1
    db.commit()
    return {"linhas_processadas": enriched, "criadas": created, "qualificadas_pelo_csv": mapped}


def import_cruzar_dados(db: Session, path: str | None = None) -> dict:
    """Cruza dados detalhados da discadora (SIP, operadores, troncos, tabulações e desligamento) a partir de cruzar_dados.csv."""
    p = Path(path or settings.cruzar_csv)
    if not p.exists():
        return {"erro": f"CSV cruzar_dados não encontrado: {p}"}

    # Tentativa de leitura com encodings comuns
    text = None
    for enc in ("latin1", "cp1252", "utf-8-sig", "utf-8"):
        try:
            text = p.read_text(encoding=enc)
            break
        except Exception:
            continue
    if not text:
        return {"erro": "Falha ao decodificar cruzar_dados.csv"}

    delim = ";" if text.split("\n", 1)[0].count(";") >= text.split("\n", 1)[0].count(",") else ","
    reader = csv.reader(io.StringIO(text), delimiter=delim)
    try:
        header = next(reader)
    except StopIteration:
        return {"linhas_processadas": 0}

    # Dicionário de chamadas indexadas por nome_arquivo e por id_ligacao
    calls_by_file = {c.nome_arquivo: c for c in db.scalars(select(Call)).all() if c.nome_arquivo}
    calls_by_id = {c.id_ligacao: c for c in db.scalars(select(Call)).all() if c.id_ligacao}

    def _norm_tab(t: str) -> str:
        t_up = _nk(t).upper()
        if "NEGOCIA" in t_up or "CONTRATO" in t_up:
            return "EM_NEGOCIACAO"
        if "NAO E O CLIENTE" in t_up or "ENGANO" in t_up:
            return "NAO_E_O_CLIENTE"
        if "NAO TEM INTERESSE" in t_up or "SEM INTERESSE" in t_up or "NAO QUER" in t_up:
            return "SEM_INTERESSE"
        if "MUDA" in t_up and "CAIXA" in t_up:
            return "MUDA_OU_CAIXA"
        if "MUDA" in t_up:
            return "LIGACAO_MUDA"
        if "CAIXA" in t_up or "SECRETARIA" in t_up:
            return "CAIXA_POSTAL"
        if "TEMPO POS" in t_up or "NAO TABULADO" in t_up or not t_up.strip():
            return "NAO_TABULADO"
        return "OUTRO"

    def _extract_reaction_time(txt: str) -> int | None:
        if not txt:
            return None
        m = re.search(r"(\d+)\s*segundo", txt)
        return int(m.group(1)) if m else None

    enriched = 0
    divergent_count = 0

    for row in reader:
        if len(row) <= 27:
            continue
        nome_arq = row[27].strip()
        cod_lig_raw = row[26].strip()
        cod_lig = int(cod_lig_raw) if cod_lig_raw.isdigit() else None

        call = calls_by_file.get(nome_arq) or (calls_by_id.get(cod_lig) if cod_lig else None)
        if not call:
            continue

        # Dados da linha
        tipo_lig = row[4].strip()
        sip_text = row[9].strip()
        telefone_csv = row[12].strip()
        tempo_reacao_str = row[14].strip()
        tab_op = row[19].strip()
        usuario_op = row[20].strip()
        grupo_orig = row[22].strip()
        tronco_val = row[23].strip()
        cliente_nome = row[3].strip()

        # Preenchimento de metadados
        if usuario_op:
            call.operador_nome = usuario_op
        if tab_op:
            call.tabulacao_operador = tab_op
        if grupo_orig:
            call.grupo_origem = grupo_orig
        if tronco_val:
            call.tronco = tronco_val
        if cliente_nome and (not call.nome_esperado or len(cliente_nome) > len(call.nome_esperado)):
            call.nome_esperado = cliente_nome
            call.cliente_identificado = cliente_nome
        if telefone_csv and not call.telefone:
            call.telefone = re.sub(r"\D", "", telefone_csv)

        reacao_seg = _extract_reaction_time(tempo_reacao_str)
        if reacao_seg is not None:
            call.tempo_reacao_operador = reacao_seg

        # Desligamento (SIP)
        if "BYE recebido" in sip_text:
            call.desligado_por = "CLIENTE"
        elif "BYE enviado" in sip_text:
            call.desligado_por = "OPERADOR"
        elif sip_text:
            call.desligado_por = "OUTRO"
        call.desligamento_detalhe = sip_text or None

        # Tipo de Agente (Célula Operacional: Grupo DIGITAL vs COMERCIAL)
        grp_up = (grupo_orig or "").upper()
        if "DIGITAL" in grp_up:
            call.tipo_agente = "DIGITAL"
        else:
            call.tipo_agente = "COMERCIAL"

        # Tipo de Discagem (Ativo vs URA)
        tr_up = (tronco_val or "").upper()
        if "URA" in grp_up or "URA" in tr_up or "RECEPTIVO" in tipo_lig.upper():
            call.tipo_discagem = "URA"
        else:
            call.tipo_discagem = "ATIVO"

        # Normalização de tabulação e cálculo de divergência
        tab_norm = _norm_tab(tab_op)
        call.tabulacao_normalizada = tab_norm

        if call.categoria:
            is_div = False
            detalhe = None
            if tab_norm == "NAO_TABULADO" and call.categoria in ("EM_NEGOCIACAO", "SEM_INTERESSE", "NAO_E_O_CLIENTE"):
                is_div = True
                detalhe = f"Operador não tabulou ({tab_op or 'Vazio'}), mas IA identificou {call.categoria}."
            elif tab_norm == "MUDA_OU_CAIXA" and call.categoria in ("LIGACAO_MUDA", "CAIXA_POSTAL"):
                is_div = False
            elif tab_norm not in ("NAO_TABULADO", "OUTRO", "MUDA_OU_CAIXA") and tab_norm != call.categoria:
                is_div = True
                detalhe = f"Operador tabulou '{tab_op}', mas IA identificou '{call.categoria}'."

            call.divergencia_tabulacao = is_div
            call.divergencia_detalhe = detalhe
            if is_div:
                divergent_count += 1

        enriched += 1

    db.commit()
    return {
        "linhas_enriquecidas": enriched,
        "divergencias_encontradas": divergent_count,
    }


def import_legacy_html(db: Session, path: str | None = None) -> dict:
    """Importa metadados enriquecidos (troncos, durações e transcrições) do dashboard_gravacoes.html."""
    import json
    p = Path(path or settings.legacy_html)
    if not p.exists():
        return {"linhas_processadas": 0, "criadas": 0}
    txt = p.read_text(encoding="utf-8", errors="ignore")
    m = re.search(r"const CALLS = (\[.*?\]);", txt, re.DOTALL)
    if not m:
        return {"linhas_processadas": 0, "criadas": 0}
    try:
        calls = json.loads(m.group(1))
    except Exception:
        return {"erro": "Falha ao decodificar JSON do HTML"}

    cats, subs = _label_index()
    enriched = created = 0
    for item in calls:
        filename = item.get("f")
        if not filename:
            continue
        meta = parse_filename(filename) or {}
        call = db.scalars(select(Call).where(Call.nome_arquivo == filename)).first()
        if call is None:
            call = Call(nome_arquivo=filename, origem="html", status="pending", **meta)
            f = Path(settings.recordings_dir) / filename
            if f.exists():
                call.caminho_audio = str(f)
            db.add(call)
            created += 1

        call.tronco = item.get("tr") or call.tronco
        call.direcionado = int(item.get("dir", 0))
        if item.get("n"):
            call.nome_esperado = item.get("n")
        if item.get("p"):
            call.telefone = item.get("p")
        if item.get("d") is not None:
            call.duracao_segundos = float(item["d"])
        if item.get("t"):
            call.transcricao = item.get("t")

        cat_label = _nk(item.get("c", ""))
        cat = cats.get(cat_label)
        if cat and call.status != "done":
            sub_label = _nk(item.get("s", ""))
            sub = _SUB_ALIAS.get(sub_label, subs.get((cat, sub_label)))
            call.categoria, call.subcategoria = cat, sub
            call.status, call.motor, call.confianca = "done", "html", 0.85
            call.resumo = "Auditado da base de gravações."
            call.conflito_identidade = sub == "E_O_CLIENTE_HISTORICO"
            call.qualificado_em = datetime.utcnow()
        enriched += 1

    db.commit()
    return {"linhas_processadas": enriched, "criadas": created}
