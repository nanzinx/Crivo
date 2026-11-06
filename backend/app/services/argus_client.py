"""Cliente da API Argus (doc-api-argus.pdf): auth por header Token-Signature."""
import base64
import ssl
from datetime import datetime
from pathlib import Path

import httpx

from ..config import settings


class ArgusError(RuntimeError):
    pass


def _client() -> httpx.Client:
    if not settings.argus_token:
        raise ArgusError("ARGUS_TOKEN não configurado")
    ctx = ssl.create_default_context()
    ctx.set_ciphers("DEFAULT:@SECLEVEL=1")
    return httpx.Client(
        base_url=settings.argus_base_url.rstrip("/"),
        timeout=120,
        verify=ctx,
        headers={"Token-Signature": settings.argus_token},
    )


def campaign_ids() -> list[int]:
    return [int(x) for x in settings.argus_campaign_ids.split(",") if x.strip().isdigit()]


def listar_gravacoes(id_campanha: int, **filtros) -> list[dict]:
    """POST /cmd/listargravacoes — exige nrLead|idSkill|codCliente|cpfCnpj|telefone."""
    with _client() as c:
        r = c.post("/cmd/listargravacoes", json={"idCampanha": id_campanha, **filtros})
        r.raise_for_status()
        j = r.json()
    if j.get("codStatus", 1) < 1:
        raise ArgusError(j.get("descStatus"))
    return j.get("retornoLigacoesItens", [])


def ligacoes_detalhadas(id_campanha: int, inicio: datetime | None = None, fim: datetime | None = None,
                        ultimos_minutos: int | None = None, id_status_ligacao: int | None = 1):
    """POST /report/ligacoesdetalhadas — gera itens paginando por idProxPagina (máx. 7 dias/consulta)."""
    body: dict = {"idCampanha": id_campanha}
    if id_status_ligacao is not None:
        body["idStatusLigacao"] = id_status_ligacao  # 1 = ATENDIMENTO
    if ultimos_minutos:
        body["ultimosMinutos"] = ultimos_minutos
    else:
        body["periodoInicial"] = inicio.strftime("%Y-%m-%d %H:%M:%S")
        body["periodoFinal"] = fim.strftime("%Y-%m-%d %H:%M:%S")
    with _client() as c:
        while True:
            r = c.post("/report/ligacoesdetalhadas", json=body)
            r.raise_for_status()
            j = r.json()
            if j.get("codStatus", 1) < 1:
                raise ArgusError(j.get("descStatus"))
            yield from j.get("ligacoesDetalhadas", [])
            if j.get("endOfTable") or not j.get("idProxPagina"):
                break
            body["ultimoId"] = j["idProxPagina"]


def download_gravacao(id_campanha: int, id_ligacao: int, pre_atendimento: bool = False) -> Path:
    """POST /cmd/downloadgravacao — salva em ARGUS_DOWNLOAD_DIR e devolve o caminho."""
    fmt = settings.argus_audio_format.upper()
    body = {"idCampanha": id_campanha, "idLigacao": id_ligacao, "formato": fmt,
            "preAtendimento": "S" if pre_atendimento else "N",
            "opcaoCanais": settings.argus_audio_channels, "base64": "S"}
    with _client() as c:
        r = c.post("/cmd/downloadgravacao", json=body)
        r.raise_for_status()
        j = r.json()
    if "arquivoBase64" not in j:
        raise ArgusError(f"Resposta sem áudio: {str(j)[:200]}")
    out_dir = Path(settings.argus_download_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"c{id_campanha}_id{id_ligacao}{'_pre' if pre_atendimento else ''}.{fmt.lower()}"
    out.write_bytes(base64.b64decode(j["arquivoBase64"]))
    return out
