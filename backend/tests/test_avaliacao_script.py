"""Monitoria, fase 2: script versionado, avaliação item a item, nota, trava e reabertura."""
import itertools
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import settings
from app.database import SessionLocal
from app.main import app
from app.models import Avaliacao, AvaliacaoEvento, Call, ScriptVersao, Sessao, Usuario
from app.services import auth, avaliacoes, script

_ids = itertools.count(960000)


def _call(**kw) -> int:
    base = dict(id_ligacao=next(_ids), status="pendente_avaliacao", caminho_audio="/tmp/x.mp3",
                data_ligacao=datetime(2025, 8, 1, 10), operador_nome="Operador Script",
                tabulacao_operador="CLIENTE NÃO TEM INTERESSE")
    with SessionLocal() as db:
        c = Call(**{**base, **kw})
        db.add(c)
        db.commit()
        return c.id


def _itens(av: dict, aplicabilidade: str | None = None) -> list[dict]:
    secoes = (av.get("script") or av)["secoes"]  # aceita a avaliação ou o próprio script
    return [i for s in secoes if aplicabilidade in (None, s["aplicabilidade"]) for i in s["itens"]]


def _marcar_tudo(av: dict, estado="acertou", desfecho="recusa") -> list[dict]:
    secs = [s for s in av["script"]["secoes"] if avaliacoes.secao_aplica(s["aplicabilidade"], desfecho)]
    return [{"item_id": i["id"], "estado": estado, "comentario": "ok" if estado != "acertou" else None}
            for s in secs for i in s["itens"]]


# --------------------------------------------------------------------------- script
def test_script_do_pdf_vem_semeado_e_ativo(client):
    s = client.get("/api/v1/scripts/ativo").json()
    assert s["status"] == "ativa" and s["numero"] >= 1
    titulos = [x["titulo"] for x in s["secoes"]]
    assert titulos[0] == "Abertura" and "Processo de efetivação da venda" in titulos
    apl = {x["titulo"]: x["aplicabilidade"] for x in s["secoes"]}
    assert apl["Processo de efetivação da venda"] == "venda" and apl["Crie necessidade no cliente"] == "recusa"
    criticos = [i for i in _itens(s, "venda") if i["critico"]]
    assert len(criticos) == 3, "efetivação: documento, anuência e texto de confirmação são críticos"
    assert any("1,67%" in i["texto"] for i in _itens(s))


def test_editar_script_cria_versao_nova_e_avaliacao_fica_presa_a_antiga(client):
    cid = _call()
    av = client.post(f"/api/v1/calls/{cid}/avaliacao").json()
    v_antiga = av["script_versao_id"]

    rasc = client.post("/api/v1/scripts/versoes").json()
    assert rasc["status"] == "rascunho" and rasc["numero"] > av["script"]["numero"]
    secoes = [{"titulo": s["titulo"], "aplicabilidade": s["aplicabilidade"],
               "itens": [{"texto": i["texto"], "peso": i["peso"], "critico": i["critico"]} for i in s["itens"]]}
              for s in rasc["secoes"]]
    secoes[0]["itens"].append({"texto": "Item novo da abertura", "peso": 2, "critico": False})
    r = client.put(f"/api/v1/scripts/versoes/{rasc['id']}", json={"nome": "Script v2", "valor_divergencia": 0.5,
                                                                   "secoes": secoes})
    assert r.status_code == 200 and r.json()["secoes"][0]["itens"][-1]["peso"] == 2
    assert client.post(f"/api/v1/scripts/versoes/{rasc['id']}/publicar").json()["status"] == "ativa"
    assert client.get("/api/v1/scripts/ativo").json()["id"] == rasc["id"]
    assert client.get(f"/api/v1/scripts/versoes/{v_antiga}").json()["status"] == "arquivada"

    # a avaliação aberta antes continua na versão antiga; uma nova usa a nova
    assert client.get(f"/api/v1/avaliacoes/{av['id']}").json()["script_versao_id"] == v_antiga
    nova = client.post(f"/api/v1/calls/{_call()}/avaliacao").json()
    assert nova["script_versao_id"] == rasc["id"]
    # versão publicada não se edita
    assert client.put(f"/api/v1/scripts/versoes/{rasc['id']}", json={"nome": "x", "secoes": secoes}).status_code == 409


# --------------------------------------------------------------------------- nota
def test_nota_divergencia_vale_meio_e_nao_se_aplica_sai_da_conta(client):
    av = client.post(f"/api/v1/calls/{_call()}/avaliacao").json()
    sempre = _itens(av, "sempre")
    marc = [{"item_id": i["id"], "estado": "acertou"} for i in sempre]
    marc[0] = {"item_id": sempre[0]["id"], "estado": "errou", "comentario": "Não falou o nome do cliente"}
    marc[1] = {"item_id": sempre[1]["id"], "estado": "divergencia", "comentario": "Falou diferente"}
    marc[2] = {"item_id": sempre[2]["id"], "estado": "nao_se_aplica"}
    r = client.put(f"/api/v1/avaliacoes/{av['id']}", json={"desfecho": "outro", "itens": marc}).json()
    pesos = sum(i["peso"] for i in sempre) - sempre[2]["peso"]
    pontos = pesos - sempre[0]["peso"] - 0.5 * sempre[1]["peso"]
    assert r["calculo"]["nota"] == round(100 * pontos / pesos, 1)
    assert r["calculo"]["falha_critica"] is False and r["calculo"]["pendentes"] == []
    assert r["calculo"]["contagem"]["errou"] == 1 and r["calculo"]["contagem"]["nao_se_aplica"] == 1


def test_secoes_condicionais_dependem_do_desfecho(client):
    av = client.post(f"/api/v1/calls/{_call()}/avaliacao").json()
    venda, recusa, sempre = _itens(av, "venda"), _itens(av, "recusa"), _itens(av, "sempre")
    r = client.put(f"/api/v1/avaliacoes/{av['id']}", json={"desfecho": "venda"}).json()
    assert set(r["calculo"]["pendentes"]) == {i["id"] for i in sempre + venda}
    r = client.put(f"/api/v1/avaliacoes/{av['id']}", json={"desfecho": "recusa"}).json()
    assert set(r["calculo"]["pendentes"]) == {i["id"] for i in sempre + recusa}
    r = client.put(f"/api/v1/avaliacoes/{av['id']}", json={"desfecho": "sem_conversa"}).json()
    assert r["calculo"]["pendentes"] == [] and r["calculo"]["nota"] is None


def test_item_critico_errado_marca_falha_critica_sem_zerar(client):
    av = client.post(f"/api/v1/calls/{_call()}/avaliacao").json()
    marc = _marcar_tudo(av, desfecho="venda")
    critico = next(i for i in _itens(av, "venda") if i["critico"])
    for m in marc:
        if m["item_id"] == critico["id"]:
            m.update(estado="errou", comentario="Não coletou o documento")
    r = client.put(f"/api/v1/avaliacoes/{av['id']}", json={"desfecho": "venda", "itens": marc}).json()
    assert r["calculo"]["falha_critica"] is True and r["calculo"]["itens_criticos_errados"] == [critico["id"]]
    assert 80 < r["calculo"]["nota"] < 100


# --------------------------------------------------------------------------- finalizar
def test_finalizar_exige_tudo_marcado_comentario_e_resultado(client):
    cid = _call()
    av = client.post(f"/api/v1/calls/{cid}/avaliacao").json()
    r = client.post(f"/api/v1/avaliacoes/{av['id']}/finalizar")
    assert r.status_code == 422
    probs = " ".join(r.json()["detail"]["problemas"])
    assert "desfecho" in probs and "categoria" in probs

    marc = _marcar_tudo(av, desfecho="recusa")
    marc[0].update(estado="errou", comentario="")
    client.put(f"/api/v1/avaliacoes/{av['id']}", json={"desfecho": "recusa", "categoria": "SEM_INTERESSE",
                                                       "itens": marc})
    r = client.post(f"/api/v1/avaliacoes/{av['id']}/finalizar")
    assert r.status_code == 422 and "sem comentário" in " ".join(r.json()["detail"]["problemas"])

    marc[0]["comentario"] = "Pulou a saudação"
    client.put(f"/api/v1/avaliacoes/{av['id']}", json={
        "itens": marc, "observacao": "Boa condução", "feedback_fortes": "Tom de voz", "feedback_melhorar": "Saudação",
        "marcas": [{"item_id": marc[0]["item_id"], "segundos": 3.5, "tipo": "errou"}, {"segundos": 40, "texto": "Ruído"}]})
    r = client.post(f"/api/v1/avaliacoes/{av['id']}/finalizar")
    assert r.status_code == 200, r.text
    f = r.json()
    assert f["status"] == "finalizada" and f["nota"] is not None and f["nota"] < 100
    assert f["feedback_melhorar"] == "Saudação" and len(f["marcas"]) == 2 and f["marcas"][0]["segundos"] == 3.5
    assert f["trava"]["ativa"] is False and [e["acao"] for e in f["eventos"]] == ["iniciada", "finalizada"]

    c = client.get(f"/api/v1/calls/{cid}").json()
    assert c["status"] == "avaliada" and c["categoria"] == "SEM_INTERESSE" and c["divergencia_tabulacao"] is False
    assert c["avaliacao"]["nota"] == f["nota"]
    # finalizada não aceita mais alterações
    assert client.put(f"/api/v1/avaliacoes/{av['id']}", json={"observacao": "x"}).status_code == 409


def test_finalizar_entra_na_divergencia(client):
    cid = _call(tabulacao_operador="CLIENTE NÃO TEM INTERESSE")
    av = client.post(f"/api/v1/calls/{cid}/avaliacao").json()
    client.put(f"/api/v1/avaliacoes/{av['id']}", json={"desfecho": "sem_conversa", "categoria": "LIGACAO_MUDA"})
    assert client.post(f"/api/v1/avaliacoes/{av['id']}/finalizar").status_code == 200
    c = client.get(f"/api/v1/calls/{cid}").json()
    assert c["divergencia_tabulacao"] is True and c["avaliacao"]["nota"] is None


def test_nao_avaliavel_exige_motivo(client):
    cid = _call()
    av = client.post(f"/api/v1/calls/{cid}/avaliacao").json()
    assert client.post(f"/api/v1/avaliacoes/{av['id']}/nao-avaliavel", json={"motivo": " "}).status_code == 422
    r = client.post(f"/api/v1/avaliacoes/{av['id']}/nao-avaliavel", json={"motivo": "Áudio cortado no meio"})
    assert r.status_code == 200 and r.json()["status"] == "nao_avaliavel"
    assert client.get(f"/api/v1/calls/{cid}").json()["status"] == "nao_avaliavel"


def test_reabrir_guarda_como_era_na_auditoria(client):
    cid = _call()
    av = client.post(f"/api/v1/calls/{cid}/avaliacao").json()
    client.put(f"/api/v1/avaliacoes/{av['id']}", json={"desfecho": "recusa", "categoria": "SEM_INTERESSE",
                                                       "itens": _marcar_tudo(av)})
    fim = client.post(f"/api/v1/avaliacoes/{av['id']}/finalizar").json()
    assert client.post(f"/api/v1/avaliacoes/{av['id']}/reabrir", json={"motivo": ""}).status_code == 422
    r = client.post(f"/api/v1/avaliacoes/{av['id']}/reabrir", json={"motivo": "Ouvi de novo: houve venda"}).json()
    assert r["status"] == "rascunho" and r["trava"]["minha"] is True
    ev = r["eventos"][-1]
    assert ev["acao"] == "reaberta" and ev["detalhe"]["antes"]["nota"] == fim["nota"]
    assert ev["detalhe"]["motivo"] == "Ouvi de novo: houve venda"
    c = client.get(f"/api/v1/calls/{cid}").json()
    assert c["status"] == "em_avaliacao" and c["categoria"] is None, "enquanto reaberta, não vale como resultado"
    # e iniciar de novo numa finalizada é recusado (tem que reabrir)
    client.put(f"/api/v1/avaliacoes/{av['id']}", json={"desfecho": "sem_conversa"})
    client.post(f"/api/v1/avaliacoes/{av['id']}/finalizar")
    assert client.post(f"/api/v1/calls/{cid}/avaliacao").status_code == 409


def test_registro_rapido_reaberto_ganha_o_script(client):
    cid = _call()
    client.post(f"/api/v1/calls/{cid}/resultado", json={"categoria": "SEM_INTERESSE"})
    a_id = client.get(f"/api/v1/calls/{cid}").json()["avaliacao"]["id"]
    r = client.post(f"/api/v1/avaliacoes/{a_id}/reabrir", json={"motivo": "avaliar o script"}).json()
    assert r["script"] is not None and r["calculo"]["pendentes"]


def test_fila_mostra_quem_esta_avaliando_e_a_meta(client):
    cid = _call(operador_nome="Operador Fila", data_ligacao=datetime(2025, 8, 2, 9))
    client.post(f"/api/v1/calls/{cid}/avaliacao")
    r = client.get("/api/v1/avaliacoes/fila", params={"operador": "Operador Fila"}).json()
    assert r["total"] == 1 and r["itens"][0]["rascunho"]["minha"] is True
    assert r["meta"]["diaria"] == 30


# --------------------------------------------------------------------------- trava
def _usuario(db, email, papel="monitora"):
    u = db.scalars(select(Usuario).where(Usuario.email == email)).first()
    return u or auth.criar_usuario(db, email, email.split("@")[0].title(), "senha-forte-1", papel)


def test_trava_impede_duas_monitoras_e_expira():
    cid = _call()
    with SessionLocal() as db:
        ana, bia = _usuario(db, "ana.trava@x.com"), _usuario(db, "bia.trava@x.com")
        db.commit()
        c = db.get(Call, cid)
        a = avaliacoes.iniciar(db, c, ana)
        db.commit()
        with pytest.raises(avaliacoes.Conflito, match="Ana.Trava está avaliando"):
            avaliacoes.iniciar(db, c, bia)
        db.rollback()
        with pytest.raises(avaliacoes.Conflito):
            avaliacoes.salvar(db, a, bia, {"observacao": "intrusa"})
        db.rollback()
        # a trava vence sozinha (a Ana fechou a aba): a Bia assume
        a.trava_ate = datetime.now() - timedelta(minutes=1)
        db.commit()
        assert avaliacoes.iniciar(db, c, bia).trava_nome == "Bia.Trava"
        db.commit()
        avaliacoes.liberar_trava(db, a, bia)
        db.commit()
        assert avaliacoes.iniciar(db, c, ana).trava_nome == "Ana.Trava"


def test_registro_rapido_respeita_a_trava():
    cid = _call()
    with SessionLocal() as db:
        ana = _usuario(db, "ana.trava@x.com")
        db.commit()
        avaliacoes.iniciar(db, db.get(Call, cid), ana)
        db.commit()
    with TestClient(app) as c:  # sem login = "Acesso local", que não é a Ana
        r = c.post(f"/api/v1/calls/{cid}/resultado", json={"categoria": "SEM_INTERESSE"})
        assert r.status_code == 409 and "Ana.Trava" in r.json()["detail"]


# --------------------------------------------------------------------------- permissões
@pytest.fixture
def com_login(monkeypatch):
    monkeypatch.setattr(settings, "auth_ativo", True)
    with TestClient(app) as c:
        yield c


def _entrar(c, email, papel):
    with SessionLocal() as db:
        _usuario(db, email, papel)
        db.commit()
    c.cookies.clear()
    assert c.post("/api/v1/auth/login", json={"email": email, "senha": "senha-forte-1"}).status_code == 200


@pytest.mark.parametrize("papel,avaliar,editar_script", [
    ("monitora", 200, 403), ("admin", 200, 200), ("supervisor", 403, 403), ("leitura", 403, 403)])
def test_permissoes_da_avaliacao(com_login, papel, avaliar, editar_script):
    _entrar(com_login, f"{papel}.perm@x.com", papel)
    assert com_login.get("/api/v1/scripts/ativo").status_code == 200, "todos leem o script"
    assert com_login.post(f"/api/v1/calls/{_call()}/avaliacao").status_code == avaliar
    assert com_login.post("/api/v1/scripts/versoes").status_code == editar_script
    assert com_login.put("/api/v1/parametros", json={"meta_diaria": "25"}).status_code == editar_script
