"""Semana 4: filtro de alucinações do Whisper, alertas automáticos, relatório diário e notificações."""
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import select

from app.config import settings
from app.database import SessionLocal
from app.models import Alerta, Call, Relatorio, agora
from app.services import ai_qualifier, alertas, notificacoes, pipeline, relatorio
from helpers import IAFalsa, fala, wav


# --------------------------------------------------------------------------- alucinações do Whisper
@pytest.mark.parametrize("texto,esperado", [
    ("Legendas pela comunidade Amara.org", ""),
    ("Obrigado.", ""),
    ("Obrigada por assistir! Inscreva-se no canal.", ""),
    ("Alô? Bom dia, falo com a dona Maria? Legendas pela comunidade Amara.org",
     "Alô? Bom dia, falo com a dona Maria?"),
    ("não tenho interesse, obrigado", "não tenho interesse, obrigado"),  # "obrigado" no meio da fala real fica
    ("Tchau. Tchau. Tchau. Tchau. Tchau.", "Tchau."),  # repetição em laço
])
def test_limpar_alucinacoes(texto, esperado):
    assert ai_qualifier.limpar_alucinacoes(texto)[0] == esperado


def test_transcricao_so_com_alucinacao_vira_muda_sem_pagar_classificacao(tmp_path, monkeypatch):
    ia = IAFalsa(monkeypatch)
    ia.fala_por_arquivo = lambda p: "Legendas pela comunidade Amara.org"
    with SessionLocal() as db:
        c = Call(id_ligacao=810001, status="pending", caminho_audio=wav(tmp_path / "h.wav", [fala(20, 1, 6)]))
        db.add(c)
        db.commit()
        pipeline.qualificar_call(db, c)
        assert (c.status, c.categoria, c.subcategoria) == ("done", "LIGACAO_MUDA", "MUDO_TOTAL")
        assert ia.classificacoes == 0 and ia.transcricoes == 1
        assert c.metricas_acusticas["alucinacoes_removidas"] == 1
        assert "alucina" in c.resumo.lower()


def test_alucinacao_parcial_e_removida_antes_da_classificacao(tmp_path, monkeypatch):
    ia = IAFalsa(monkeypatch)
    ia.fala_por_arquivo = lambda p: "Não tenho interesse. Obrigado por assistir!"
    with SessionLocal() as db:
        c = Call(id_ligacao=810002, status="pending", caminho_audio=wav(tmp_path / "h2.wav", [fala(20, 1, 6)]))
        db.add(c)
        db.commit()
        pipeline.qualificar_call(db, c)
        assert ia.textos[-1] == "Não tenho interesse."
        assert c.transcricao == "Não tenho interesse."


# --------------------------------------------------------------------------- notificações
class _Resp:
    def raise_for_status(self):
        pass


def test_sem_canal_configurado_nada_e_enviado(monkeypatch):
    monkeypatch.setattr(settings, "notificar_webhook_url", "")
    monkeypatch.setattr(settings, "smtp_host", "")
    r = notificacoes.enviar("Assunto", "texto")
    assert r["enviado"] is False and "configur" in r["motivo"].lower()


def test_webhook_e_email(monkeypatch):
    enviados = {}
    monkeypatch.setattr(settings, "notificar_webhook_url", "https://hooks.exemplo.com/abc")
    monkeypatch.setattr(settings, "smtp_host", "smtp.exemplo.com")
    monkeypatch.setattr(settings, "notificar_emails", "a@exemplo.com, b@exemplo.com")
    monkeypatch.setattr(settings, "smtp_remetente", "crivo@exemplo.com")
    monkeypatch.setattr(notificacoes.httpx, "post", lambda url, json, timeout: enviados.setdefault("webhook", (url, json)) and _Resp())

    class SMTPFalso:
        def __init__(self, host, port, timeout):
            enviados["smtp"] = (host, port)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def starttls(self):
            enviados["tls"] = True

        def login(self, u, s):
            enviados["login"] = u

        def send_message(self, msg):
            enviados["msg"] = msg

    monkeypatch.setattr(notificacoes.smtplib, "SMTP", SMTPFalso)
    r = notificacoes.enviar("Crivo: teste", "linha 1", "<p>linha 1</p>")
    assert r["enviado"] is True and set(r["canais"]) == {"webhook", "email"}
    url, corpo = enviados["webhook"]
    assert url.endswith("/abc") and "Crivo: teste" in corpo["text"] and "linha 1" in corpo["text"]
    assert enviados["msg"]["To"] == "a@exemplo.com, b@exemplo.com" and enviados["msg"]["Subject"] == "Crivo: teste"


def test_falha_num_canal_nao_impede_o_outro(monkeypatch):
    monkeypatch.setattr(settings, "notificar_webhook_url", "https://hooks.exemplo.com/abc")
    monkeypatch.setattr(settings, "smtp_host", "")

    def _explode(*a, **k):
        raise RuntimeError("timeout")

    monkeypatch.setattr(notificacoes.httpx, "post", _explode)
    r = notificacoes.enviar("x", "y")
    assert r["enviado"] is False and "timeout" in r["erros"]["webhook"]


# --------------------------------------------------------------------------- alertas
@pytest.fixture
def capturar(monkeypatch):
    msgs = []
    monkeypatch.setattr(notificacoes, "enviar", lambda assunto, texto, html=None: msgs.append((assunto, texto)) or {"enviado": True})
    return msgs


def _calls(db, n, base, agora_, **kw):
    for i in range(n):
        db.add(Call(id_ligacao=base + i, status="done", data_ligacao=agora_ - timedelta(minutes=30 + i),
                    confianca=0.9, **kw))
    db.commit()


def test_alerta_de_operador_abre_atualiza_e_resolve(capturar):
    t = agora()
    with SessionLocal() as db:
        _calls(db, 18, 820000, t, operador_nome="Operador Alerta", categoria="SEM_INTERESSE")
        _calls(db, 7, 820100, t, operador_nome="Operador Alerta", categoria="EM_NEGOCIACAO",
               divergencia_tabulacao=True, divergencia_gravidade="alta")
        r = alertas.avaliar(db, t)
        a = db.scalars(select(Alerta).where(Alerta.chave == "operador:Operador Alerta")).one()
        assert a.resolvido_em is None and a.nivel == "critico", "7 divergências altas (>= 5)"
        assert "28%" in a.mensagem and "operador=Operador+Alerta" in a.link
        assert r["novos"] >= 1 and any("Operador Alerta" in m[1] for m in capturar)

        n_msgs = len(capturar)
        alertas.avaliar(db, t + timedelta(minutes=15))  # continua igual: não notifica de novo
        assert len(capturar) == n_msgs
        assert db.scalars(select(Alerta).where(Alerta.chave == "operador:Operador Alerta")).all() == [a]

        alertas.avaliar(db, t + timedelta(days=2))  # fora da janela: condição sumiu
        db.refresh(a)
        assert a.resolvido_em is not None


def test_operador_com_poucas_ligacoes_nao_gera_alerta(capturar):
    t = agora()
    with SessionLocal() as db:
        _calls(db, 4, 821000, t, operador_nome="Operador Poucas", categoria="EM_NEGOCIACAO",
               divergencia_tabulacao=True, divergencia_gravidade="alta")
        alertas.avaliar(db, t)
        assert db.scalars(select(Alerta).where(Alerta.chave == "operador:Operador Poucas")).first() is None


def test_alerta_de_tronco_com_pico_de_mudas(capturar):
    t = agora()
    with SessionLocal() as db:
        _calls(db, 15, 822000, t, tronco="TRONCO RUIM", categoria="LIGACAO_MUDA")
        _calls(db, 10, 822100, t, tronco="TRONCO RUIM", categoria="SEM_INTERESSE")
        _calls(db, 2, 822200, t, tronco="TRONCO BOM", categoria="LIGACAO_MUDA")
        _calls(db, 23, 822300, t, tronco="TRONCO BOM", categoria="SEM_INTERESSE")
        alertas.avaliar(db, t)
        ruim = db.scalars(select(Alerta).where(Alerta.chave == "tronco:TRONCO RUIM")).one()
        assert "60%" in ruim.mensagem and "8%" in ruim.mensagem
        assert db.scalars(select(Alerta).where(Alerta.chave == "tronco:TRONCO BOM")).first() is None


def test_alerta_de_nao_ligar_sem_registro(capturar):
    t = agora()
    with SessionLocal() as db:
        _calls(db, 2, 823000, t, categoria="SEM_INTERESSE", pediu_nao_ligar=True, divergencia_tabulacao=True,
               divergencia_gravidade="alta", divergencia_detalhe="O cliente pediu para não ligar mais, mas ...")
        alertas.avaliar(db, t)
        a = db.scalars(select(Alerta).where(Alerta.chave == "nao_ligar", Alerta.resolvido_em.is_(None))).one()
        assert "LGPD" in a.titulo and "nao_ligar=true" in a.link


def test_api_de_alertas(client, capturar):
    r = client.post("/api/v1/alertas/avaliar")
    assert r.status_code == 200
    lista = client.get("/api/v1/alertas").json()
    assert {"abertos", "recentes", "canais", "regras"} <= set(lista)
    if lista["abertos"]:
        aid = lista["abertos"][0]["id"]
        rec = client.post(f"/api/v1/alertas/{aid}/reconhecer", json={"por": "Supervisora Ana"}).json()
        assert rec["reconhecido_por"] == "Supervisora Ana"


# --------------------------------------------------------------------------- relatório diário
def test_relatorio_do_dia(client, capturar):
    dia = date(2026, 3, 10)
    with SessionLocal() as db:
        base = datetime(2026, 3, 10, 10)
        for i in range(6):
            db.add(Call(id_ligacao=830000 + i, status="done", data_ligacao=base + timedelta(minutes=i),
                        operador_nome="Op Relatório", categoria="SEM_INTERESSE", confianca=0.9,
                        tabulacao_operador="CLIENTE NÃO TEM INTERESSE", tronco="T1",
                        divergencia_tabulacao=i < 2, divergencia_gravidade="alta" if i < 2 else None))
        db.commit()
        rel = relatorio.gerar(db, dia)
        d = rel.dados
        assert d["total"] == 6 and d["divergencias"]["total"] == 2
        assert d["operadores"][0]["operador"] == "Op Relatório"
        assert "6 ligações" in rel.texto and "Op Relatório" in rel.texto
        assert "<table" in relatorio.html(rel)
        # gerar de novo o mesmo dia substitui (um relatório por dia)
        relatorio.gerar(db, dia)
        assert len(db.scalars(select(Relatorio).where(Relatorio.data == dia)).all()) == 1

    r = client.post("/api/v1/relatorios/gerar", params={"data": "2026-03-10", "enviar": "true"}).json()
    assert r["dados"]["total"] == 6 and r["envio"]["enviado"] is True
    assert any("10/03/2026" in assunto for assunto, _ in capturar)
    lista = client.get("/api/v1/relatorios").json()
    assert any(x["data"] == "2026-03-10" for x in lista["itens"])
    assert "<table" in client.get(f"/api/v1/relatorios/{r['id']}/html").text


@pytest.mark.parametrize("agora_,ultimo,esperado", [
    (datetime(2026, 11, 20, 19, 5), None, True),  # sexta, 19h
    (datetime(2026, 11, 20, 18, 59), None, False),  # antes do horário
    (datetime(2026, 11, 20, 19, 30), date(2026, 11, 20), False),  # já gerado hoje
    (datetime(2026, 11, 22, 19, 30), None, False),  # domingo
])
def test_quando_gerar_o_relatorio(monkeypatch, agora_, ultimo, esperado):
    monkeypatch.setattr(settings, "relatorio_hora", 19)
    monkeypatch.setattr(settings, "relatorio_dias", "0-5")
    assert relatorio.deve_gerar(agora_, ultimo) is esperado


def test_teste_de_notificacao_pela_api(client, capturar):
    assert client.post("/api/v1/notificacoes/teste").json()["enviado"] is True
