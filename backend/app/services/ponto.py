"""Controle de ponto: importa os CSVs do Argus e monta os relatórios da planilha "Controle de Ponto - Argus".

Regras copiadas das macros da planilha (MontarRelatorio), para os números baterem:
- Entrada = o horário mais cedo do operador no dia; saída = o mais tarde (pode haver mais de uma linha).
- Atraso: compara a entrada com o turno previsto mais próximo do grupo ("08:30;14:00" = dois turnos) e só conta
  acima da tolerância; o atraso é arredondado em minutos (arredondamento bancário, como o Round do VBA).
- Grupo com "Entra no relatório = NÃO" sai (ex.: URA PORT, operadores virtuais); operador com o texto de
  "ignorar" no nome também (ex.: TESTE). Grupo novo entra com SIM (URA PORT e SEM SUPERVISOR entram com NÃO).
- Almoço: início e fim do almoço mais longo; tempo = soma de todos os almoços do dia.
- TMP = tempo total nas pausas que contam (pausa nova conta; o almoço tem colunas próprias); QTP = quantas.
- Pausas só contam para quem está no relatório de entrada/saída, e só as que começaram no dia.
- Relatório "entrada" (o de hoje, com o dia em andamento) mostra só entrada e atraso.
"""
import csv
import io
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from ..models import (Call, Operador, Parametro, PontoGrupo, PontoImportacao, PontoJornada, PontoPausa,
                      PontoPausaConfig, agora)

# configuração inicial = aba Config da planilha
GRUPOS_PADRAO = [
    ("ARIEL - COMERCIAL", True, "10:00", 10), ("CAHUAN - COMERCIAL", True, "10:00", 10),
    ("GABRIEL - COMERCIAL", True, "10:00", 10), ("MAYSA - COMERCIAL", True, "10:00", 10),
    ("DIGITAL", True, "08:30;14:00", 10), ("RECEPTIVO - URA", True, "08:30;10:00", 10),
    ("SEM SUPERVISOR", False, "", 10), ("URA PORT - 1", False, "", 10),
]
PAUSAS_PADRAO = [("Almoço", False)] + [(p, True) for p in (
    "Banheiro", "CADASTRANDO VENDA", "Chamada de Video", "Em Atendimento - DIGITAL", "ENVIAR PROPOSTA", "Feedback",
    "Formalização/Desbloqueio", "LIGAÇÃO - DISCADORA", "LIGAÇÃO - WPP", "NOVO LEAD", "PESQUISANDO LEAD",
    "PLANO DE AÇÃO", "RETENÇÃO", "TREINAMENTO")]
PARAMETROS = {"ponto_almoco": "Almoço", "ponto_ignorar": "TESTE"}


class ArquivoInvalido(ValueError):
    pass


# --------------------------------------------------------------------------- leitura (como LerTexto/LerCsv)
def decodificar(dados: bytes) -> str:
    """O Argus exporta em Windows-1252; aceita UTF-8 (com ou sem BOM) também."""
    try:
        return dados.decode("utf-8-sig")
    except UnicodeDecodeError:
        return dados.decode("cp1252")


def ler_csv(dados: bytes) -> list[list[str]]:
    texto = decodificar(dados)
    primeira = texto.split("\n", 1)[0]
    sep = ";" if primeira.count(";") >= primeira.count(",") else ","
    return [[c.strip() for c in linha] for linha in csv.reader(io.StringIO(texto), delimiter=sep) if any(c.strip() for c in linha)]


def tipo(linhas: list[list[str]]) -> str | None:
    if len(linhas) < 2:
        return None
    cab = "|".join(linhas[0]).upper()
    if "PAUSA" in cab:
        return "pausas"
    if "GRUPO ATUAL" in cab and "ENTRADA" in cab:
        return "ponto"
    return None


def hora_seg(s: str | None) -> int | None:
    """'09:58' / '00:02:09' -> segundos (HoraParaNum). Vazio ou inválido -> None."""
    s = (s or "").strip()
    if ":" not in s:
        return None
    p = s.split(":")
    try:
        seg = int(p[0]) * 3600 + int(p[1]) * 60 + (int(p[2]) if len(p) > 2 and p[2].strip() else 0)
    except ValueError:
        return None
    return seg


def texto_data(s: str | None) -> date | None:
    """'2026-11-26' ou '26/11/2026 16:44:25' -> date (TextoParaData)."""
    s = (s or "").strip().split(" ")[0]
    try:
        if "-" in s:
            a, m, d = s.split("-")
            return date(int(a), int(m), int(d))
        if "/" in s:
            d, m, a = s.split("/")
            return date(int(a), int(m), int(d))
    except ValueError:
        return None
    return None


def texto_datahora(s: str | None) -> datetime | None:
    d = texto_data(s)
    if d is None:
        return None
    partes = (s or "").strip().split(" ", 1)
    seg = hora_seg(partes[1]) if len(partes) > 1 else None
    seg = seg or 0
    return datetime(d.year, d.month, d.day, seg // 3600 % 24, seg // 60 % 60, seg % 60)


def _col(cab: list[str], *nomes: str) -> int | None:
    norm = [_sem_acento(c).upper().strip() for c in cab]
    for n in nomes:
        n = _sem_acento(n).upper()
        for i, c in enumerate(norm):
            if c == n:
                return i
    return None


def _sem_acento(s: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFD", s or "") if unicodedata.category(ch) != "Mn")


def chave(nome: str | None) -> str:
    """Chave do operador: sem acento, maiúsculas, espaços simples (casa ponto × ligações)."""
    return " ".join(_sem_acento(nome or "").upper().split())


# --------------------------------------------------------------------------- importação
@dataclass
class Resultado:
    arquivo: str
    tipo: str | None = None
    data: date | None = None
    linhas: int = 0
    erro: str | None = None
    substituiu: bool = False


def importar(db: Session, arquivo: str, dados: bytes, usuario: str | None = None) -> Resultado:
    """Importa um CSV do Argus (reconhece sozinho se é entrada/saída ou pausas). Mesma data = substitui."""
    res = Resultado(arquivo=arquivo)
    try:
        linhas = ler_csv(dados)
    except Exception as e:  # noqa: BLE001
        res.erro = f"não foi possível ler o arquivo ({e})"
        return res
    res.tipo = tipo(linhas)
    if res.tipo is None:
        res.erro = "não parece um relatório de entrada/saída nem de pausas do Argus"
        return res
    cab, corpo = linhas[0], linhas[1:]
    if res.tipo == "ponto":
        ci = {k: _col(cab, *n) for k, n in {"data": ("Data",), "grupo": ("Grupo Atual",), "op": ("Operador",),
                                             "ent": ("Entrada",), "sai": ("Saída", "Saida")}.items()}
        if None in (ci["data"], ci["op"], ci["ent"]):
            res.erro = "faltam colunas Data, Operador ou Entrada"
            return res
        g = lambda row, k: row[ci[k]] if ci[k] is not None and ci[k] < len(row) else ""  # noqa: E731
        res.data = next((d for row in corpo if (d := texto_data(g(row, "data")))), None)
    else:
        ci = {k: _col(cab, *n) for k, n in {"grupo": ("Grupo Operacional",), "op": ("Operador",),
                                             "desc": ("Descrição da Pausa", "Descricao da Pausa"),
                                             "ini": ("Inicio", "Início"), "fim": ("Fim",), "tempo": ("Tempo",)}.items()}
        if None in (ci["op"], ci["desc"], ci["ini"]):
            res.erro = "faltam colunas Operador, Descrição da Pausa ou Início"
            return res
        g = lambda row, k: row[ci[k]] if ci[k] is not None and ci[k] < len(row) else ""  # noqa: E731
        res.data = next((d for row in corpo if (d := texto_data(g(row, "ini")))), None)
    if res.data is None:
        res.erro = "não encontrei a data do relatório"
        return res

    antigas = db.scalars(select(PontoImportacao).where(PontoImportacao.tipo == res.tipo,
                                                       PontoImportacao.data_ref == res.data)).all()
    for imp in antigas:  # mesma data de novo: a última importação vale
        alvo = PontoJornada if res.tipo == "ponto" else PontoPausa
        db.query(alvo).filter(alvo.importacao_id == imp.id).delete(synchronize_session=False)
        db.delete(imp)
        res.substituiu = True
    imp = PontoImportacao(tipo=res.tipo, data_ref=res.data, arquivo=arquivo[:200], importado_por=usuario)
    db.add(imp)
    db.flush()

    if res.tipo == "ponto":
        for row in corpo:
            nome = g(row, "op").strip()
            if not nome:
                continue
            db.add(PontoJornada(importacao_id=imp.id, data=texto_data(g(row, "data")) or res.data,
                                grupo=g(row, "grupo").strip() or None, operador=nome,
                                entrada_seg=hora_seg(g(row, "ent")), saida_seg=hora_seg(g(row, "sai"))))
            res.linhas += 1
    else:
        for row in corpo:
            nome = g(row, "op").strip()
            if not nome:
                continue
            ini = texto_datahora(g(row, "ini"))
            db.add(PontoPausa(importacao_id=imp.id, data=ini.date() if ini else res.data,
                              grupo=g(row, "grupo").strip() or None, operador=nome, descricao=g(row, "desc").strip()[:120],
                              inicio=ini, fim=texto_datahora(g(row, "fim")), segundos=max(0, hora_seg(g(row, "tempo")) or 0)))
            res.linhas += 1
    imp.linhas = res.linhas
    db.flush()
    sincronizar_config(db)
    if res.tipo == "ponto":
        atualizar_operadores(db, res.data)
    return res


def sincronizar_config(db: Session) -> None:
    """Grupos e pausas novos entram na configuração sozinhos (como SincronizarConfig da planilha)."""
    conhecidos = {g.casefold() for g in db.scalars(select(PontoGrupo.grupo))}
    novos = set(db.scalars(select(PontoJornada.grupo).distinct())) | set(db.scalars(select(PontoPausa.grupo).distinct()))
    for g in sorted(x for x in novos if x):
        if g.casefold() not in conhecidos:
            fora = "URA PORT" in g.upper() or "SEM SUPERVISOR" in g.upper()
            db.add(PontoGrupo(grupo=g, incluir=not fora, entrada_prevista="", tolerancia_min=10))
            conhecidos.add(g.casefold())
    almoco = parametro(db, "ponto_almoco").upper()
    pausas = {p.casefold() for p in db.scalars(select(PontoPausaConfig.descricao))}
    for p in sorted(x for x in db.scalars(select(PontoPausa.descricao).distinct()) if x):
        if p.casefold() not in pausas:
            db.add(PontoPausaConfig(descricao=p, conta=p.upper() != almoco))
            pausas.add(p.casefold())
    db.flush()


def atualizar_operadores(db: Session, dia: date) -> int:
    """Equipe de cada operador = "Grupo Atual" do ponto mais recente. Preenche a equipe das ligações sem equipe
    (e das que estavam com a equipe antiga, a partir do dia do ponto)."""
    t = agora()
    rows = db.execute(select(PontoJornada.operador, PontoJornada.grupo).where(PontoJornada.data == dia)).all()
    atual = {chave(op): (op, g) for op, g in rows if g}
    for k, (op, g) in atual.items():
        o = db.get(Operador, k)
        if o is None:
            db.add(Operador(chave=k, nome=op, grupo=g, atualizado_em=t))
        elif o.atualizado_em is None or dia >= o.atualizado_em.date() or o.grupo is None:
            o.nome, o.grupo, o.atualizado_em = op, g, t
    db.flush()
    return preencher_equipes(db)


def preencher_equipes(db: Session) -> int:
    """Ligações sem equipe ganham a equipe do operador (cadastro vindo do ponto)."""
    mapa = {o.chave: o.grupo for o in db.scalars(select(Operador).where(Operador.grupo.is_not(None)))}
    if not mapa:
        return 0
    n = 0
    for cid, nome in db.execute(select(Call.id, Call.operador_nome)
                                .where(Call.grupo_origem.is_(None), Call.operador_nome.is_not(None))).all():
        g = mapa.get(chave(nome))
        if g:
            db.execute(update(Call).where(Call.id == cid).values(grupo_origem=g))
            n += 1
    return n


def equipe_do_operador(db: Session, nome: str | None) -> str | None:
    o = db.get(Operador, chave(nome)) if nome else None
    return o.grupo if o else None


# --------------------------------------------------------------------------- configuração
def parametro(db: Session, k: str) -> str:
    p = db.get(Parametro, k)
    return p.valor if p else PARAMETROS[k]


def seed_se_vazio(db: Session) -> bool:
    if db.scalar(select(func.count()).select_from(PontoGrupo)) or db.scalar(select(func.count()).select_from(PontoPausaConfig)):
        return False
    db.add_all(PontoGrupo(grupo=g, incluir=i, entrada_prevista=e, tolerancia_min=t) for g, i, e, t in GRUPOS_PADRAO)
    db.add_all(PontoPausaConfig(descricao=p, conta=c) for p, c in PAUSAS_PADRAO)
    return True


def _grupos(db: Session) -> dict[str, PontoGrupo]:
    return {g.grupo.casefold(): g for g in db.scalars(select(PontoGrupo))}


def _pausas_conta(db: Session) -> dict[str, bool]:
    return {p.descricao.casefold(): bool(p.conta) for p in db.scalars(select(PontoPausaConfig))}


def minutos_atraso(cfg: PontoGrupo | None, entrada_seg: int | None) -> int:
    """MinutosAtraso: turno previsto mais próximo; só acima da tolerância; Round bancário em minutos."""
    if entrada_seg is None or cfg is None:
        return 0
    melhor = None
    for txt in (cfg.entrada_prevista or "").replace(",", ";").split(";"):
        h = hora_seg(txt)
        if h is None:
            continue
        dif = entrada_seg - h
        if melhor is None or abs(dif) < abs(melhor):
            melhor = dif
    if melhor is None:
        return 0
    minutos = melhor / 60
    return int(round(minutos)) if minutos > (cfg.tolerancia_min or 0) + 0.0001 else 0


# --------------------------------------------------------------------------- relatório (MontarRelatorio)
@dataclass
class Linha:
    operador: str
    grupo: str | None
    entrada: int | None = None
    saida: int | None = None
    almoco_inicio: datetime | None = None
    almoco_fim: datetime | None = None
    almoco_seg: int | None = None
    tmp_seg: int | None = None
    qtp: int | None = None
    atraso_min: int = 0
    _almoco_maior: int = field(default=-1, repr=False)

    @property
    def jornada_seg(self) -> int | None:
        return self.saida - self.entrada if self.entrada is not None and self.saida is not None else None

    def to_dict(self) -> dict:
        iso = lambda d: d.isoformat() if d else None  # noqa: E731
        return {"operador": self.operador, "grupo": self.grupo, "entrada_seg": self.entrada, "saida_seg": self.saida,
                "jornada_seg": self.jornada_seg, "almoco_inicio": iso(self.almoco_inicio), "almoco_fim": iso(self.almoco_fim),
                "almoco_seg": self.almoco_seg, "tmp_seg": self.tmp_seg, "qtp": self.qtp, "atraso_min": self.atraso_min,
                "observacao": f"Atraso de {self.atraso_min} min" if self.atraso_min else None}


def relatorio(db: Session, dia: date, completo: bool = True, grupos_visiveis: list[str] | None = None) -> list[Linha]:
    grupos = _grupos(db)
    pausas_conta = _pausas_conta(db)
    ignorar = parametro(db, "ponto_ignorar").strip().upper()
    almoco = parametro(db, "ponto_almoco").strip().upper()

    ops: dict[str, Linha] = {}
    for j in db.scalars(select(PontoJornada).where(PontoJornada.data == dia).order_by(PontoJornada.id)):
        nome, grupo = j.operador.strip(), (j.grupo or "").strip()
        if not nome or (ignorar and ignorar in nome.upper()):
            continue
        cfg = grupos.get(grupo.casefold())
        if cfg is not None and not cfg.incluir:
            continue
        k = nome.casefold()
        if k in ops:
            v = ops[k]
            if j.entrada_seg is not None and (v.entrada is None or j.entrada_seg < v.entrada):
                v.entrada = j.entrada_seg
            if j.saida_seg is not None and (v.saida is None or j.saida_seg > v.saida):
                v.saida = j.saida_seg
        else:
            ops[k] = Linha(operador=nome, grupo=grupo or None, entrada=j.entrada_seg, saida=j.saida_seg)

    if completo:
        for p in db.scalars(select(PontoPausa).where(PontoPausa.data == dia).order_by(PontoPausa.id)):
            v = ops.get(p.operador.strip().casefold())
            if v is None or p.inicio is None or p.inicio.date() != dia:
                continue
            if v.tmp_seg is None:
                v.tmp_seg, v.qtp = 0, 0
            seg = p.segundos or 0
            if p.descricao.strip().upper() == almoco:
                if seg > v._almoco_maior:  # almoço principal = o mais longo
                    v.almoco_inicio, v.almoco_fim, v._almoco_maior = p.inicio, p.fim, seg
                v.almoco_seg = (v.almoco_seg or 0) + seg
            elif pausas_conta.get(p.descricao.strip().casefold(), True):
                v.tmp_seg += seg
                v.qtp += 1
        for v in ops.values():
            if v.almoco_seg == 0:
                v.almoco_seg = None  # a planilha deixa em branco
    else:
        for v in ops.values():
            v.saida = None

    for v in ops.values():
        v.atraso_min = minutos_atraso(grupos.get((v.grupo or "").casefold()), v.entrada)
    linhas = sorted(ops.values(), key=lambda v: (_sem_acento(v.operador).casefold(), v.operador.casefold()))
    if grupos_visiveis is not None:
        linhas = [v for v in linhas if v.grupo in grupos_visiveis]
    return linhas


def resumo(linhas: list[Linha], completo: bool) -> dict:
    almocos = [v.almoco_seg for v in linhas if v.almoco_seg]
    tmps = [v.tmp_seg for v in linhas if v.tmp_seg is not None]
    return {
        "operadores": len(linhas),
        "presentes": sum(1 for v in linhas if v.entrada is not None),
        "atrasos": sum(1 for v in linhas if v.atraso_min),
        "almoco_medio_seg": round(sum(almocos) / len(almocos)) if completo and almocos else None,
        "almoco_acima_1h": sum(1 for a in almocos if a > 3600) if completo else None,
        "tmp_medio_seg": round(sum(tmps) / len(tmps)) if completo and tmps else None,
    }
