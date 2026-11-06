"""Importa gravações locais (padrão Argus no nome do arquivo), o CSV de escuta legado,
o HTML legado e o relatório detalhado da discadora (cruzar_dados.csv)."""
import csv
import io
import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Call, agora
from . import pipeline

FILE_RE = re.compile(
    r"^(?P<data>\d{4}-\d{2}-\d{2})_(?P<hora>\d{6})_nr(?P<nr>\d+)_id(?P<id>\d+)_(?P<tel>\d+)_(?P<nome>.*)\.(?:mp3|wav)$",
    re.I,
)


def parse_filename(name: str) -> dict | None:
    m = FILE_RE.match(name)
    if not m:
        return None
    dt = datetime.strptime(m["data"] + m["hora"], "%Y-%m-%d%H%M%S")
    return {"data_ligacao": dt, "nr_lead": int(m["nr"]), "id_ligacao": int(m["id"]),
            "telefone": m["tel"], "nome_esperado": m["nome"].strip() or None}


def _nk(s: str) -> str:
    s = unicodedata.normalize("NFD", (s or "").strip().lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def _decode(raw: bytes) -> str:
    """UTF-8 primeiro (latin1 nunca falha, então tentá-lo antes corrompia acentos de arquivos UTF-8)."""
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin1")


def _delim(text: str) -> str:
    first = text.split("\n", 1)[0]
    return ";" if first.count(";") >= first.count(",") else ","


def vincular_ou_criar(db: Session, nome_arq: str, meta: dict, origem: str,
                      caminho: str | None = None) -> tuple[Call, str]:
    """Acha a ligação pelo nome do arquivo ou pelo id_ligacao (ex.: já veio do webhook Argus).

    Retorna (call, 'existente' | 'vinculada' | 'nova'). Evita o IntegrityError que derrubava a
    importação inteira quando o mesmo id_ligacao já existia com outra origem.
    """
    call = db.scalars(select(Call).where(Call.nome_arquivo == nome_arq)).first()
    acao = "existente"
    if call is None and meta.get("id_ligacao"):
        call = db.scalars(select(Call).where(Call.id_ligacao == meta["id_ligacao"])).first()
        if call is not None:
            acao = "vinculada"
            call.nome_arquivo = call.nome_arquivo or nome_arq
    if call is None:
        call = Call(nome_arquivo=nome_arq, origem=origem, status="pending", **meta)
        db.add(call)
        acao = "nova"
    else:
        for k, v in meta.items():  # completa só o que estiver vazio
            if v is not None and getattr(call, k) is None:
                setattr(call, k, v)
    if caminho and not call.caminho_audio:
        call.caminho_audio = caminho
    db.flush()
    return call, acao


def import_folder(db: Session, folder: str | None = None, limit: int | None = None) -> dict:
    folder_p = Path(folder or settings.recordings_dir)
    if not folder_p.exists():
        return {"novas": 0, "vinculadas": 0, "ignoradas": 0, "erro": f"Pasta não encontrada: {folder_p}"}
    existing = set(db.scalars(select(Call.nome_arquivo).where(Call.nome_arquivo.is_not(None))).all())
    new = linked = skipped = 0
    for f in sorted(folder_p.glob("*.*")):
        if f.suffix.lower() not in (".mp3", ".wav") or f.name in existing:
            skipped += 1
            continue
        meta = parse_filename(f.name)
        if not meta:
            skipped += 1
            continue
        _, acao = vincular_ou_criar(db, f.name, meta, "local", str(f))
        new += acao == "nova"
        linked += acao == "vinculada"
        if limit and new >= limit:
            break
    db.commit()
    return {"novas": new, "vinculadas": linked, "ignoradas": skipped}


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
    "ja possui / sem margem": "JA_POSSUI",
    "ja possui": "JA_POSSUI",
    "sem margem": "JA_POSSUI",
    "atendente solitario": "ATENDENTE_SOLITARIO",
    "cliente solitario": "CLIENTE_SOLITARIO",
    "falha de comunicacao": "FALHA_COMUNICACAO",
    "caixa postal": None,
}


def _caminho_local(nome_arq: str) -> str | None:
    f = Path(settings.recordings_dir) / nome_arq
    return str(f) if f.exists() else None


def import_legacy_csv(db: Session, path: str | None = None) -> dict:
    """Importa o relatório da escuta manual/anterior. Aceita ';' ou ',' e cabeçalhos com/sem acento."""
    p = Path(path or settings.legacy_csv)
    if not p.exists():
        return {"erro": f"CSV não encontrado: {p}"}
    cats, subs = _label_index()
    text = _decode(p.read_bytes())
    reader = csv.DictReader(io.StringIO(text), delimiter=_delim(text))
    reader.fieldnames = [_nk(h) for h in reader.fieldnames or []]
    enriched = created = mapped = 0
    for row in reader:
        nome_arq = (row.get("arquivo") or "").strip()
        meta = parse_filename(nome_arq)
        if not meta:
            continue
        call, acao = vincular_ou_criar(db, nome_arq, meta, "csv", _caminho_local(nome_arq))
        created += acao == "nova"
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
            call.qualificado_em = agora()
            pipeline.calcular_divergencia(call)
            mapped += 1
        enriched += 1
    db.commit()
    return {"linhas_processadas": enriched, "criadas": created, "qualificadas_pelo_csv": mapped}


# --------------------------------------------------------------------------- cruzar_dados.csv
# Cada campo: apelidos aceitos no cabeçalho (normalizados, sem acento) + posição legada de fallback.
_COLUNAS_CRUZAR: dict[str, tuple[list[str], int]] = {
    "arquivo": (["arquivo", "nome arquivo", "gravacao", "arquivo gravacao"], 27),
    "cod_ligacao": (["cod. ligacao", "cod ligacao", "codigo ligacao", "codigo da ligacao", "id ligacao",
                     "idligacao"], 26),
    "cliente": (["cliente", "nome cliente", "nome do cliente"], 3),
    "tipo_ligacao": (["tipo ligacao", "tipo de ligacao"], 4),
    "sip": (["sinalizacao sip", "sinalizacao", "sip", "motivo desligamento", "desligamento"], 9),
    "telefone": (["telefone", "fone", "numero discado"], 12),
    "tempo_reacao": (["tempo de reacao", "tempo reacao", "reacao"], 14),
    "tabulacao": (["tabulacao", "tabulacao operador"], 19),
    "usuario": (["usuario", "operador", "agente", "nome usuario"], 20),
    "grupo": (["grupo origem", "grupo de origem", "grupo"], 22),
    "tronco": (["tronco", "rota"], 23),
}


def _resolver_colunas(header: list[str]) -> tuple[dict[str, int], list[str]]:
    """Mapeia campo -> índice pelo nome do cabeçalho. Retorna também os campos achados só por posição."""
    norm = [_nk(h) for h in header]
    idx: dict[str, int] = {}
    usados: set[int] = set()
    for campo, (apelidos, _) in _COLUNAS_CRUZAR.items():  # 1º: igualdade exata
        for i, h in enumerate(norm):
            if i not in usados and h in apelidos:
                idx[campo] = i
                usados.add(i)
                break
    for campo, (apelidos, _) in _COLUNAS_CRUZAR.items():  # 2º: começa com o apelido
        if campo in idx:
            continue
        for i, h in enumerate(norm):
            if i not in usados and any(h.startswith(a) for a in apelidos):
                idx[campo] = i
                usados.add(i)
                break
    por_posicao = []
    if len(idx) < 3:  # cabeçalho irreconhecível: usa o layout legado por posição (e avisa)
        for campo, (_, pos) in _COLUNAS_CRUZAR.items():
            if campo not in idx and pos < len(header):
                idx[campo] = pos
                por_posicao.append(campo)
    return idx, por_posicao


def _tipo_agente(grupo: str) -> str | None:
    g = (grupo or "").upper()
    if not g.strip():
        return None  # sem grupo => desconhecido (antes virava COMERCIAL e inflava a equipe)
    return "DIGITAL" if "DIGITAL" in g else "COMERCIAL"


def _tipo_discagem(grupo: str, tronco: str, tipo_lig: str) -> str | None:
    g, t, tl = (grupo or "").upper(), (tronco or "").upper(), (tipo_lig or "").upper()
    if "URA" in g or "URA" in t or "RECEPTIVO" in tl:
        return "URA"
    if g.strip() or t.strip() or tl.strip():
        return "ATIVO"
    return None


def _desligado_por(sip: str) -> str | None:
    if "BYE recebido" in sip:
        return "CLIENTE"
    if "BYE enviado" in sip:
        return "OPERADOR"
    return "OUTRO" if sip else None


def import_cruzar_dados(db: Session, path: str | None = None, conteudo: bytes | None = None) -> dict:
    """Cruza o relatório detalhado da discadora (SIP, operador, tronco, tabulação, desligamento)
    com as ligações já importadas. Lê pelas colunas do cabeçalho; aceita UTF-8 ou Windows-1252."""
    if conteudo is None:
        p = Path(path or settings.cruzar_csv)
        if not p.exists():
            return {"erro": f"CSV de cruzamento não encontrado: {p}", "linhas_enriquecidas": 0}
        conteudo = p.read_bytes()
    text = _decode(conteudo)
    reader = csv.reader(io.StringIO(text), delimiter=_delim(text))
    header = next(reader, None)
    if not header:
        return {"linhas_enriquecidas": 0, "divergencias_encontradas": 0}
    col, por_posicao = _resolver_colunas(header)
    if "arquivo" not in col and "cod_ligacao" not in col:
        return {"erro": "Cabeçalho sem coluna de arquivo nem de código da ligação.", "linhas_enriquecidas": 0,
                "cabecalho": header}

    def get(row: list[str], campo: str) -> str:
        i = col.get(campo)
        return row[i].strip() if i is not None and i < len(row) else ""

    calls_by_file = {c.nome_arquivo: c for c in db.scalars(select(Call).where(Call.nome_arquivo.is_not(None)))}
    calls_by_id = {c.id_ligacao: c for c in db.scalars(select(Call).where(Call.id_ligacao.is_not(None)))}

    enriched = divergent = sem_match = 0
    for row in reader:
        if not any(x.strip() for x in row):
            continue
        cod = get(row, "cod_ligacao")
        call = calls_by_file.get(get(row, "arquivo")) or (calls_by_id.get(int(cod)) if cod.isdigit() else None)
        if not call:
            sem_match += 1
            continue

        usuario, tab, grupo, tronco = get(row, "usuario"), get(row, "tabulacao"), get(row, "grupo"), get(row, "tronco")
        cliente, tel, sip = get(row, "cliente"), get(row, "telefone"), get(row, "sip")
        if usuario:
            call.operador_nome = usuario
        if tab:
            call.tabulacao_operador = tab
        if grupo:
            call.grupo_origem = grupo
        if tronco:
            call.tronco = tronco
        if cliente and (not call.nome_esperado or len(cliente) > len(call.nome_esperado)):
            call.nome_esperado = cliente
            call.cliente_identificado = cliente
        if tel and not call.telefone:
            call.telefone = re.sub(r"\D", "", tel)
        if m := re.search(r"(\d+)\s*segundo", get(row, "tempo_reacao")):
            call.tempo_reacao_operador = int(m.group(1))
        if sip:
            call.desligado_por = _desligado_por(sip)
            call.desligamento_detalhe = sip
        call.tipo_agente = _tipo_agente(call.grupo_origem or "") or call.tipo_agente
        call.tipo_discagem = _tipo_discagem(call.grupo_origem or "", call.tronco or "", get(row, "tipo_ligacao")) \
            or call.tipo_discagem

        pipeline.calcular_divergencia(call)  # mesma regra usada após a qualificação da IA
        divergent += bool(call.divergencia_tabulacao)
        enriched += 1

    db.commit()
    out = {"linhas_enriquecidas": enriched, "divergencias_encontradas": divergent, "sem_correspondencia": sem_match}
    if por_posicao:
        out["aviso"] = ("Cabeçalho não reconhecido; colunas lidas pela posição do layout antigo: "
                        + ", ".join(por_posicao))
    return out


def import_legacy_html(db: Session, path: str | None = None) -> dict:
    """Importa metadados enriquecidos (troncos, durações e transcrições) do dashboard_gravacoes.html."""
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
        call, acao = vincular_ou_criar(db, filename, meta, "html", _caminho_local(filename))
        created += acao == "nova"

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

        cat = cats.get(_nk(item.get("c", "")))
        if cat and call.status != "done":
            sub_label = _nk(item.get("s", ""))
            sub = _SUB_ALIAS.get(sub_label, subs.get((cat, sub_label)))
            call.categoria, call.subcategoria = cat, sub
            call.status, call.motor, call.confianca = "done", "html", 0.85
            call.resumo = "Auditado da base de gravações."
            call.conflito_identidade = sub == "E_O_CLIENTE_HISTORICO"
            call.qualificado_em = agora()
            pipeline.calcular_divergencia(call)
        enriched += 1

    db.commit()
    return {"linhas_processadas": enriched, "criadas": created}
