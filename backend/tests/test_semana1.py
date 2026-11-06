"""Regressões das correções da semana 1 (dados confiáveis + painel de saúde)."""
from datetime import datetime

import pytest
from sqlalchemy import select

from app.config import settings
from app.database import SessionLocal
from app.models import Call
from app.services import ai_qualifier, argus_client, local_ingestor, pipeline, sincronizador


# --------------------------------------------------------------------------- 1. falha da IA
def test_falha_da_ia_marca_erro_e_preserva_transcricao(monkeypatch, tmp_path):
    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"\x00" * 64)
    monkeypatch.setattr(settings, "openai_api_key", "sk-teste")
    monkeypatch.setattr(ai_qualifier, "_cliente_openai", lambda: object())
    monkeypatch.setattr(ai_qualifier, "transcrever_audio", lambda client, path: "alô, quem fala? não conheço")

    def _explode(*a, **k):
        raise RuntimeError("429 rate limit")

    monkeypatch.setattr(ai_qualifier, "_classificar_texto", _explode)

    with SessionLocal() as db:
        call = Call(id_ligacao=310001, caminho_audio=str(audio), status="pending")
        db.add(call)
        db.commit()
        pipeline.qualificar_call(db, call)
        db.refresh(call)
        assert call.status == "error"
        assert call.categoria is None, "não pode inventar 'Ligação Muda' quando a IA falha"
        assert call.transcricao == "alô, quem fala? não conheço"
        assert "429" in (call.erro or "")


def test_falha_na_transcricao_tambem_vira_erro(monkeypatch, tmp_path):
    audio = tmp_path / "b.mp3"
    audio.write_bytes(b"\x00" * 64)
    monkeypatch.setattr(settings, "openai_api_key", "sk-teste")
    monkeypatch.setattr(ai_qualifier, "_cliente_openai", lambda: object())

    def _explode(*a, **k):
        raise TimeoutError("timeout whisper")

    monkeypatch.setattr(ai_qualifier, "transcrever_audio", _explode)
    with SessionLocal() as db:
        call = Call(id_ligacao=310002, caminho_audio=str(audio), status="pending")
        db.add(call)
        db.commit()
        pipeline.qualificar_call(db, call)
        assert call.status == "error" and call.categoria is None


# --------------------------------------------------------------------------- 2/3/4. cruzamento
CRUZAR_HEADER = [
    "Arquivo", "Cód. Ligação", "Tronco", "Grupo Origem", "Usuário", "Tabulação",
    "Tempo de Reação", "Telefone", "Sinalização SIP", "Tipo Ligação", "Cliente",
]


def _linha(arquivo, cod, tronco="4NET - BENCONSIG", grupo="", usuario="Ana Souza",
           tab="CLIENTE NÃO TEM INTERESSE", sip="Atendimento: BYE recebido.", cliente="MARIA DA SILVA"):
    return [arquivo, str(cod), tronco, grupo, usuario, tab, "Reagiu em 4 segundos", "(11) 98888-0000",
            sip, "ATIVO", cliente]


def _escreve_csv(path, linhas, sep=";", encoding="utf-8-sig"):
    txt = "\n".join(sep.join(l) for l in [CRUZAR_HEADER, *linhas])
    path.write_text(txt, encoding=encoding)


@pytest.fixture
def pastas(tmp_path, monkeypatch):
    rec = tmp_path / "gravacoes"
    rec.mkdir()
    monkeypatch.setattr(settings, "recordings_dir", str(rec))
    monkeypatch.setattr(settings, "legacy_csv", str(tmp_path / "nao_existe.csv"))
    monkeypatch.setattr(settings, "legacy_html", str(tmp_path / "nao_existe.html"))
    monkeypatch.setattr(settings, "cruzar_csv", str(tmp_path / "cruzar_dados.csv"))
    return tmp_path, rec


def test_sync_local_executa_o_cruzamento_lendo_por_cabecalho(client, pastas):
    tmp, rec = pastas
    nome = "2026-11-05_081849_nr1_id320001_11988880000_MARIA DA SILVA.mp3"
    (rec / nome).write_bytes(b"\x00" * 32)
    _escreve_csv(tmp / "cruzar_dados.csv", [_linha(nome, 320001)])

    r = client.post("/api/v1/sync/local")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["cruzamento"]["linhas_enriquecidas"] == 1

    with SessionLocal() as db:
        c = db.scalars(select(Call).where(Call.id_ligacao == 320001)).one()
        assert c.tronco == "4NET - BENCONSIG"
        assert c.operador_nome == "Ana Souza"
        assert c.tabulacao_operador == "CLIENTE NÃO TEM INTERESSE"
        assert c.desligado_por == "CLIENTE"
        assert c.tempo_reacao_operador == 4
        assert c.tabulacao_normalizada == "SEM_INTERESSE"


def test_cruzamento_le_csv_utf8_sem_corromper_acentos(pastas):
    tmp, _ = pastas
    with SessionLocal() as db:
        db.add(Call(id_ligacao=320101, nome_arquivo="x320101.mp3", status="pending"))
        db.commit()
        _escreve_csv(tmp / "cruzar_dados.csv", [_linha("x320101.mp3", 320101, usuario="João Ávila")])
        local_ingestor.import_cruzar_dados(db)
        c = db.scalars(select(Call).where(Call.id_ligacao == 320101)).one()
        assert c.operador_nome == "João Ávila"


def test_cruzamento_aceita_upload_em_cp1252(client):
    with SessionLocal() as db:
        db.add(Call(id_ligacao=320201, nome_arquivo="x320201.mp3", status="pending"))
        db.commit()
    txt = "\n".join(";".join(l) for l in [CRUZAR_HEADER, _linha("x320201.mp3", 320201, usuario="Conceição")])
    r = client.post("/api/v1/sync/cruzar", files={"arquivo": ("cruzar.csv", txt.encode("cp1252"), "text/csv")})
    assert r.status_code == 200, r.text
    assert r.json()["linhas_enriquecidas"] == 1
    with SessionLocal() as db:
        assert db.scalars(select(Call).where(Call.id_ligacao == 320201)).one().operador_nome == "Conceição"


def test_grupo_vazio_nao_vira_comercial(pastas):
    tmp, _ = pastas
    with SessionLocal() as db:
        db.add(Call(id_ligacao=320301, nome_arquivo="x320301.mp3", status="pending"))
        db.add(Call(id_ligacao=320302, nome_arquivo="x320302.mp3", status="pending"))
        db.commit()
        _escreve_csv(tmp / "cruzar_dados.csv", [
            _linha("x320301.mp3", 320301, grupo=""),
            _linha("x320302.mp3", 320302, grupo="EQUIPE DIGITAL"),
        ])
        local_ingestor.import_cruzar_dados(db)
        a = db.scalars(select(Call).where(Call.id_ligacao == 320301)).one()
        b = db.scalars(select(Call).where(Call.id_ligacao == 320302)).one()
        assert a.tipo_agente is None
        assert b.tipo_agente == "DIGITAL"


def test_divergencia_do_cruzamento_usa_a_mesma_regra_do_pipeline(pastas):
    tmp, _ = pastas
    with SessionLocal() as db:
        db.add(Call(id_ligacao=320401, nome_arquivo="x320401.mp3", status="done", categoria="SEM_INTERESSE",
                    divergencia_tabulacao=True, divergencia_detalhe="antigo"))
        db.commit()
        _escreve_csv(tmp / "cruzar_dados.csv", [_linha("x320401.mp3", 320401, tab="SEM INTERESSE")])
        local_ingestor.import_cruzar_dados(db)
        c = db.scalars(select(Call).where(Call.id_ligacao == 320401)).one()
        assert c.divergencia_tabulacao is False and c.divergencia_detalhe is None


# --------------------------------------------------------------------------- 5. colisão de id_ligacao
def test_importar_pasta_vincula_ligacao_que_ja_veio_do_argus(pastas):
    _, rec = pastas
    with SessionLocal() as db:
        db.add(Call(id_ligacao=330001, origem="argus", status="error", erro="download: falhou"))
        db.commit()
        nome = "2026-11-05_090000_nr9_id330001_11977776666_JOSE.mp3"
        (rec / nome).write_bytes(b"\x00" * 32)
        res = local_ingestor.import_folder(db)
        assert res["vinculadas"] == 1 and res["novas"] == 0
        calls = db.scalars(select(Call).where(Call.id_ligacao == 330001)).all()
        assert len(calls) == 1
        assert calls[0].caminho_audio.endswith(nome)
        assert calls[0].nome_arquivo == nome
        assert calls[0].telefone == "11977776666"


# --------------------------------------------------------------------------- 6. polling + saúde
def test_falha_no_polling_fica_registrada_na_saude(client, monkeypatch):
    monkeypatch.setattr(argus_client, "campaign_ids", lambda: [7])

    def _explode(*a, **k):
        raise argus_client.ArgusError("Token inválido")

    monkeypatch.setattr(argus_client, "ligacoes_detalhadas", _explode)
    res = sincronizador.sincronizar_recentes(15)
    assert res["ok"] is False

    s = client.get("/api/v1/saude").json()
    ev = s["eventos"]["argus_polling"]
    assert ev["ok"] is False and "Token inválido" in ev["detalhe"]
    assert any(a["nivel"] == "critico" for a in s["alertas"])


def test_polling_com_sucesso_registra_e_enfileira(client, monkeypatch):
    monkeypatch.setattr(argus_client, "campaign_ids", lambda: [7])
    monkeypatch.setattr(argus_client, "ligacoes_detalhadas", lambda *a, **k: iter([
        {"idLigacao": 340001, "dataInicioLigacao": "2026-11-06 10:00:00", "tempoLigacao": 12}]))
    res = sincronizador.sincronizar_recentes(15)
    assert res["ok"] is True and res["ligacoes"] == 1
    ev = client.get("/api/v1/saude").json()["eventos"]["argus_polling"]
    assert ev["ok"] is True and ev["ultimo_sucesso_em"]


def test_webhook_registra_ultimo_recebimento(client):
    client.post("/api/v1/webhooks/argus", json={"idTipoWebhook": 1, "idLigacao": 350001})
    s = client.get("/api/v1/saude").json()
    assert s["eventos"]["argus_webhook"]["ok"] is True
    for k in ("fila", "status_ligacoes", "integracoes", "erros_recentes", "alertas"):
        assert k in s


# --------------------------------------------------------------------------- 8. métricas coerentes
def test_timeline_respeita_filtro_de_categoria(client):
    with SessionLocal() as db:
        db.add_all([
            Call(id_ligacao=360001, status="done", categoria="CAIXA_POSTAL", data_ligacao=datetime(2025, 1, 2, 9)),
            Call(id_ligacao=360002, status="done", categoria="SEM_INTERESSE", data_ligacao=datetime(2025, 1, 2, 9)),
        ])
        db.commit()
    tl = client.get("/api/v1/analytics/timeline",
                    params={"data_inicio": "2025-01-02", "data_fim": "2025-01-02", "categoria": "CAIXA_POSTAL"}).json()
    assert tl == [{"data": "2025-01-02", "CAIXA_POSTAL": 1}]


def test_taxa_de_divergencia_do_operador_usa_so_ligacoes_qualificadas(client):
    with SessionLocal() as db:
        db.add_all([
            Call(id_ligacao=370001, operador_nome="OP RATIO", status="done", categoria="SEM_INTERESSE",
                 divergencia_tabulacao=True, data_ligacao=datetime(2025, 2, 1, 9)),
            Call(id_ligacao=370002, operador_nome="OP RATIO", status="pending", data_ligacao=datetime(2025, 2, 1, 9)),
        ])
        db.commit()
    s = client.get("/api/v1/analytics/summary", params={"operador": "OP RATIO"}).json()
    op = next(o for o in s["ranking_operadores"] if o["operador"] == "OP RATIO")
    assert op["qualificadas"] == 1 and op["taxa_divergencia"] == 100.0
