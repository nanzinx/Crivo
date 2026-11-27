"""Integra com a API do Argus o que antes vinha de planilha: operadores/equipes e o controle de ponto.

- Operadores (/cmd/listarusuarios): nome, ramal, grupo e supervisor de cada operador. Atualiza o cadastro de
  operadores e preenche a equipe das ligações (o webhook manda só o ramal e o nome do operador).
- Ponto (/report/entradasaida e /report/pausasdetalhadas): monta as mesmas tabelas dos CSVs exportados do
  Argus e usa o mesmo importador (mesmas regras da planilha). Reimportar um dia substitui.

A documentação da API não lista os campos de cada linha dos relatórios de ponto. Os nomes são reconhecidos por
aproximação (ex.: "nomeUsuario" ou "operador"); se faltar algum campo essencial, o erro mostra os campos
recebidos, para ajustar o mapeamento (ver scripts/argus_diagnostico.py).
"""
import logging
import unicodedata
from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Operador, PontoImportacao, agora
from . import argus_client, ponto, status

log = logging.getLogger("argus_operacao")


# --------------------------------------------------------------------------- operadores
def sincronizar_operadores(db: Session) -> dict:
    campanhas = set(argus_client.campaign_ids())
    usuarios = argus_client.listar_usuarios(ativo=None)
    t, n, inativos = agora(), 0, 0
    for u in usuarios:
        nome = (u.get("nome") or "").strip()
        if not nome:
            continue
        vinc = [c for c in (u.get("campanhas") or []) if not campanhas or c.get("idCampanha") in campanhas]
        principal = next((c for c in vinc if c.get("grupoUsuarioDesc")), None)
        k = ponto.chave(nome)
        o = db.get(Operador, k) or Operador(chave=k, nome=nome)
        o.nome, o.ramal, o.id_usuario_argus = nome, (str(u["ramal"]).strip() if u.get("ramal") else o.ramal), u.get("idUsuario")
        o.ativo = bool(u.get("ativo", True))
        if principal:
            o.grupo = principal["grupoUsuarioDesc"].strip()
            o.supervisor_argus = (principal.get("nomeUsuarioSupervisor") or "").strip() or None
        o.origem, o.atualizado_em = "argus", t
        db.add(o)
        n += 1
        inativos += int(not o.ativo)
    db.flush()
    preenchidas = ponto.preencher_equipes(db)
    return {"operadores": n, "inativos": inativos, "ligacoes_com_equipe": preenchidas}


def equipe_por_ramal(db: Session, ramal: str | None) -> str | None:
    if not ramal:
        return None
    return db.scalar(select(Operador.grupo).where(Operador.ramal == str(ramal).strip(), Operador.grupo.is_not(None)).limit(1))


# --------------------------------------------------------------------------- ponto pela API
def _norm(k: str) -> str:
    k = "".join(ch for ch in unicodedata.normalize("NFD", k or "") if unicodedata.category(ch) != "Mn")
    return "".join(ch for ch in k.lower() if ch.isalnum())


CAMPOS_PONTO = {
    "data": ("data", "datareferencia", "dia", "dataponto"),
    "grupo": ("grupoatual", "grupousuariodesc", "grupooperacional", "grupo", "grupodesc"),
    "operador": ("operador", "nomeusuario", "nomeoperador", "usuariooperador", "usuario", "nome"),
    "entrada": ("entrada", "horaentrada", "dataentrada", "datahoraentrada", "primeiraentrada", "login", "datalogin"),
    "saida": ("saida", "horasaida", "datasaida", "datahorasaida", "ultimasaida", "logout", "datalogout"),
}
CAMPOS_PAUSA = {
    "grupo": ("grupooperacional", "grupoatual", "grupousuariodesc", "grupo"),
    "operador": ("operador", "nomeusuario", "nomeoperador", "usuariooperador", "usuario", "nome"),
    "descricao": ("descricaodapausa", "descricaopausa", "pausadesc", "pausa", "descpausa", "motivopausa", "descricao"),
    "inicio": ("inicio", "datainicio", "iniciopausa", "datahorainicio", "datainiciopausa"),
    "fim": ("fim", "datafim", "fimpausa", "datahorafim", "datafimpausa"),
    "tempo": ("tempo", "tempopausa", "duracao", "tempoemsegundos", "segundos", "tempototal"),
}


def _pega(item: dict, nomes: tuple[str, ...]):
    norm = {_norm(k): v for k, v in item.items()}
    for n in nomes:
        if n in norm and norm[n] not in (None, ""):
            return norm[n]
    return None


def _texto(v) -> str:
    return "" if v is None else str(v).strip().replace("T", " ")


def _hora(v) -> str:
    """'2026-11-26 09:58:00' / '09:58' / '09:58:00' -> '09:58:00'"""
    s = _texto(v)
    return s.split(" ")[-1] if s else ""


def _duracao(v) -> str:
    if isinstance(v, (int, float)) or (isinstance(v, str) and v.strip().isdigit()):
        seg = int(float(v))
        return f"{seg // 3600:02d}:{seg // 60 % 60:02d}:{seg % 60:02d}"
    return _texto(v)


class FormatoInesperado(argus_client.ArgusError):
    pass


def _faltando(itens: list[dict], campos: dict, obrigatorios: tuple[str, ...]) -> None:
    if not itens:
        return
    falta = [c for c in obrigatorios if _pega(itens[0], campos[c]) is None]
    if falta:
        raise FormatoInesperado(f"o relatório do Argus veio sem {', '.join(falta)}. Campos recebidos: "
                                f"{', '.join(sorted(itens[0].keys()))}")


def tabela_ponto(itens: list[dict], dia: date) -> list[list[str]]:
    _faltando(itens, CAMPOS_PONTO, ("operador", "entrada"))
    linhas = [["Data", "Grupo Atual", "Operador", "Entrada", "Saída"]]
    for it in itens:
        ent = _texto(_pega(it, CAMPOS_PONTO["entrada"]))
        data = _texto(_pega(it, CAMPOS_PONTO["data"])) or (ent.split(" ")[0] if " " in ent else dia.isoformat())
        linhas.append([data.split(" ")[0], _texto(_pega(it, CAMPOS_PONTO["grupo"])), _texto(_pega(it, CAMPOS_PONTO["operador"])),
                       _hora(ent), _hora(_pega(it, CAMPOS_PONTO["saida"]))])
    return linhas


def tabela_pausas(itens: list[dict]) -> list[list[str]]:
    _faltando(itens, CAMPOS_PAUSA, ("operador", "descricao", "inicio"))
    linhas = [["", "Grupo Operacional", "Operador", "Descrição da Pausa", "Inicio", "Fim", "Tempo"]]
    for it in itens:
        linhas.append(["", _texto(_pega(it, CAMPOS_PAUSA["grupo"])), _texto(_pega(it, CAMPOS_PAUSA["operador"])),
                       _texto(_pega(it, CAMPOS_PAUSA["descricao"])), _texto(_pega(it, CAMPOS_PAUSA["inicio"])),
                       _texto(_pega(it, CAMPOS_PAUSA["fim"])), _duracao(_pega(it, CAMPOS_PAUSA["tempo"]))])
    return linhas


def importar_ponto(db: Session, dia: date, pausas: bool = True) -> dict:
    """Busca no Argus o ponto (e as pausas) de um dia e importa como se fossem os CSVs."""
    ini, fim = datetime.combine(dia, time.min), datetime.combine(dia, time(23, 59, 59))
    out = {"data": dia.isoformat()}
    itens = list(argus_client.entradas_saidas(ini, fim))
    if itens:
        r = ponto.importar_tabela(db, f"API Argus · entrada/saída {dia.strftime('%d/%m')}", tabela_ponto(itens, dia), "Argus (API)")
        out["ponto"] = {"linhas": r.linhas, "erro": r.erro}
    else:
        out["ponto"] = {"linhas": 0, "erro": None}
    if pausas:
        itens = list(argus_client.pausas_detalhadas(ini, fim))
        if itens:
            r = ponto.importar_tabela(db, f"API Argus · pausas {dia.strftime('%d/%m')}", tabela_pausas(itens), "Argus (API)")
            out["pausas"] = {"linhas": r.linhas, "erro": r.erro}
    return out


def ciclo(db: Session, t: datetime | None = None) -> dict:
    """Rodado periodicamente: operadores, ponto de hoje e (uma vez) o de ontem fechado."""
    t = t or agora()
    out: dict = {}
    try:
        out["operadores"] = sincronizar_operadores(db)
        db.commit()
        status.registrar(status.OPERADORES, True, f"{out['operadores']['operadores']} operadores do Argus")
    except Exception as e:  # noqa: BLE001
        db.rollback()
        status.registrar(status.OPERADORES, False, f"listarusuarios: {e}")
    try:
        out["hoje"] = importar_ponto(db, t.date())
        ontem = t.date() - timedelta(days=1)
        fechado = db.scalar(select(PontoImportacao.id).where(
            PontoImportacao.tipo == "pausas", PontoImportacao.data_ref == ontem,
            PontoImportacao.importado_em >= datetime.combine(t.date(), time.min)))
        if not fechado:  # ontem, completo, depois da meia-noite
            out["ontem"] = importar_ponto(db, ontem)
        db.commit()
        status.registrar(status.PONTO, True, f"ponto de {t.strftime('%d/%m')}: {out['hoje']['ponto']['linhas']} linhas")
    except Exception as e:  # noqa: BLE001
        db.rollback()
        status.registrar(status.PONTO, False, f"ponto pela API: {e}")
    return out
