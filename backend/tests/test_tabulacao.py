"""Semana 2: modelo de tabulação (catálogo editável), divergência por gravidade e taxonomia v2."""
from datetime import datetime

import pytest
from sqlalchemy import select

from app.database import SessionLocal
from app.models import Call, Tabulacao
from app.services import avaliacoes, pipeline, tabulacoes
from app.taxonomy import TAXONOMIA_VERSAO, valid


# --------------------------------------------------------------------------- sugestão inicial
@pytest.mark.parametrize("texto,tipo,cats,sub,nao_ligar", [
    ("LIGAÇÃO MUDA / CAIXA POSTAL", "resultado", ["LIGACAO_MUDA", "CAIXA_POSTAL"], None, False),
    ("CLIENTE NÃO TEM INTERESSE", "resultado", ["SEM_INTERESSE"], None, False),
    ("Não é o cliente", "resultado", ["NAO_E_O_CLIENTE"], None, False),
    ("EM NEGOCIAÇÃO", "resultado", ["EM_NEGOCIACAO"], None, False),
    ("Retorno agendado", "resultado", ["EM_NEGOCIACAO"], "AGENDAMENTO_RETORNO", False),
    ("Enviado por WhatsApp", "resultado", ["EM_NEGOCIACAO"], "MIGRACAO_WHATSAPP", False),
    ("Titular falecido", "resultado", ["NAO_E_O_CLIENTE"], "TITULAR_FALECIDO", False),
    ("NÃO LIGAR / BLOQUEIO", "resultado", ["SEM_INTERESSE", "NAO_E_O_CLIENTE"], None, True),
    ("TEMPO PÓS ATENDIMENTO", "nao_tabulado", [], None, False),
    ("", "nao_tabulado", [], None, False),
    ("Código 47", "ignorar", [], None, False),
])
def test_sugestao_inicial(texto, tipo, cats, sub, nao_ligar):
    r = tabulacoes.sugerir(texto)
    assert (r.tipo, r.categorias, r.subcategoria, r.nao_ligar, r.confirmada) == (tipo, cats, sub, nao_ligar, False)


def test_chave_ignora_acento_caixa_e_espacos():
    assert tabulacoes.chave("  Ligação  muda / Caixa postal ") == tabulacoes.chave("LIGACAO MUDA/CAIXA POSTAL")


# --------------------------------------------------------------------------- catálogo
def test_catalogo_registra_cada_tabulacao_uma_vez_e_liga_as_ligacoes():
    with SessionLocal() as db:
        a = Call(id_ligacao=610001, tabulacao_operador="Ligação Muda / Caixa Postal (catálogo)", status="pendente")
        b = Call(id_ligacao=610002, tabulacao_operador="LIGACAO MUDA/CAIXA POSTAL  (CATALOGO) ", status="pendente")
        db.add_all([a, b])
        db.flush()
        pipeline.atualizar_divergencia(db, a)
        pipeline.atualizar_divergencia(db, b)
        db.commit()
        assert a.tabulacao_id and a.tabulacao_id == b.tabulacao_id
        row = db.get(Tabulacao, a.tabulacao_id)
        assert row.nome == "Ligação Muda / Caixa Postal (catálogo)" and row.confirmada is False
        assert row.categorias == ["LIGACAO_MUDA", "CAIXA_POSTAL"]


def test_id_do_argus_tem_prioridade_e_e_anexado_ao_texto_existente():
    with SessionLocal() as db:
        a = Call(id_ligacao=610011, tabulacao_operador="Sem interesse (cód)", status="pendente")
        db.add(a)
        db.flush()
        pipeline.atualizar_divergencia(db, a)
        b = Call(id_ligacao=610012, tabulacao_operador="Sem interesse (cód)", id_tabulacao_argus=9911, status="pendente")
        c = Call(id_ligacao=610013, tabulacao_operador="Texto renomeado no Argus", id_tabulacao_argus=9911, status="pendente")
        db.add_all([b, c])
        db.flush()
        pipeline.atualizar_divergencia(db, b)
        pipeline.atualizar_divergencia(db, c)
        db.commit()
        assert a.tabulacao_id == b.tabulacao_id == c.tabulacao_id
        assert db.get(Tabulacao, a.tabulacao_id).id_argus == 9911


# --------------------------------------------------------------------------- regras de comparação
def _regra(**kw):
    base = dict(tipo="resultado", categorias=["SEM_INTERESSE"], subcategoria=None, nao_ligar=False, confirmada=True)
    return tabulacoes.Regra(**{**base, **kw})


def _avaliada(cat, sub=None, **kw):
    return Call(tabulacao_operador="X", status="avaliada", categoria=cat, subcategoria=sub, **kw)


def test_tabulacao_que_aceita_mais_de_uma_categoria():
    r = _regra(categorias=["LIGACAO_MUDA", "CAIXA_POSTAL"])
    for cat in ("LIGACAO_MUDA", "CAIXA_POSTAL"):
        c = _avaliada(cat)
        pipeline.calcular_divergencia(c, r)
        assert c.divergencia_tabulacao is False
    c = _avaliada("SEM_INTERESSE")
    pipeline.calcular_divergencia(c, r)
    assert c.divergencia_tabulacao is True


def test_tabulacao_ignorada_nunca_gera_divergencia():
    c = _avaliada("EM_NEGOCIACAO")
    pipeline.calcular_divergencia(c, _regra(tipo="ignorar", categorias=[]))
    assert c.divergencia_tabulacao is False and c.tabulacao_normalizada == "OUTRO"


def test_subcategoria_mapeada_gera_divergencia_baixa():
    r = _regra(categorias=["EM_NEGOCIACAO"], subcategoria="AGENDAMENTO_RETORNO")
    c = _avaliada("EM_NEGOCIACAO", "PROPOSTA_EM_ANDAMENTO")
    pipeline.calcular_divergencia(c, r)
    assert c.divergencia_tabulacao is True and c.divergencia_gravidade == "baixa"
    assert "subcategoria" in c.divergencia_detalhe.lower()
    ok = _avaliada("EM_NEGOCIACAO", "AGENDAMENTO_RETORNO")
    pipeline.calcular_divergencia(ok, r)
    assert ok.divergencia_tabulacao is False and ok.divergencia_gravidade is None


@pytest.mark.parametrize("tipo,esperadas,ia,gravidade", [
    # oportunidade perdida / negociação que não existiu
    ("resultado", ["SEM_INTERESSE"], "EM_NEGOCIACAO", "alta"),
    ("resultado", ["EM_NEGOCIACAO"], "LIGACAO_MUDA", "alta"),
    ("nao_tabulado", [], "EM_NEGOCIACAO", "alta"),
    # houve conversa, mas foi tabulada como sem contato (o problema recente)
    ("resultado", ["LIGACAO_MUDA", "CAIXA_POSTAL"], "NAO_E_O_CLIENTE", "alta"),
    ("resultado", ["CAIXA_POSTAL"], "SEM_INTERESSE", "alta"),
    # erros entre resultados de conversa, ou tabulou conversa e não houve
    ("resultado", ["SEM_INTERESSE"], "NAO_E_O_CLIENTE", "media"),
    ("resultado", ["NAO_E_O_CLIENTE"], "CAIXA_POSTAL", "media"),
    ("nao_tabulado", [], "SEM_INTERESSE", "media"),
    # confusão entre "sem contato"
    ("resultado", ["CAIXA_POSTAL"], "LIGACAO_MUDA", "baixa"),
])
def test_gravidade_da_divergencia(tipo, esperadas, ia, gravidade):
    c = _avaliada(ia)
    pipeline.calcular_divergencia(c, _regra(tipo=tipo, categorias=esperadas))
    assert c.divergencia_tabulacao is True and c.divergencia_gravidade == gravidade


def test_coerente_limpa_gravidade_antiga():
    c = _avaliada("SEM_INTERESSE", divergencia_gravidade="alta", divergencia_tabulacao=True)
    pipeline.calcular_divergencia(c, _regra())
    assert c.divergencia_tabulacao is False and c.divergencia_gravidade is None


# --------------------------------------------------------------------------- pedido de não ligar (LGPD)
def test_pedido_de_nao_ligar_sem_registro_e_divergencia_alta():
    c = _avaliada("SEM_INTERESSE", "CLIENTE_REVOLTADO", pediu_nao_ligar=True)
    pipeline.calcular_divergencia(c, _regra(), nao_ligar_ativo=True)
    assert c.divergencia_tabulacao is True and c.divergencia_gravidade == "alta"
    assert "não ligar" in c.divergencia_detalhe


def test_pedido_de_nao_ligar_registrado_na_tabulacao_certa_e_coerente():
    c = _avaliada("SEM_INTERESSE", pediu_nao_ligar=True)
    pipeline.calcular_divergencia(c, _regra(categorias=["SEM_INTERESSE", "NAO_E_O_CLIENTE"], nao_ligar=True),
                                  nao_ligar_ativo=True)
    assert c.divergencia_tabulacao is False


def test_sem_tabulacao_de_nao_ligar_no_argus_o_pedido_nao_vira_divergencia():
    """Se o Argus não tem como registrar o pedido, cobrar o operador seria injusto: só lista."""
    c = _avaliada("SEM_INTERESSE", pediu_nao_ligar=True)
    pipeline.calcular_divergencia(c, _regra(), nao_ligar_ativo=False)
    assert c.divergencia_tabulacao is False


# --------------------------------------------------------------------------- taxonomia v2
def test_taxonomia_v2():
    assert TAXONOMIA_VERSAO == 2
    for cat, sub in (("LIGACAO_MUDA", "DESLIGOU_NA_ABERTURA"), ("LIGACAO_MUDA", "LIGACAO_CAIU"),
                     ("SEM_INTERESSE", "JA_E_CLIENTE"), ("INDETERMINADO", "AUDIO_INAUDIVEL")):
        assert valid(cat, sub)


def test_avaliacao_grava_versao_da_taxonomia_e_pedido():
    with SessionLocal() as db:
        c = Call(id_ligacao=620001, status="pendente_avaliacao", tabulacao_operador="CLIENTE NÃO TEM INTERESSE")
        db.add(c)
        db.flush()
        avaliacoes.registrar_resultado(db, c, "SEM_INTERESSE", "CLIENTE_REVOLTADO", pediu_nao_ligar=True,
                                       monitora_nome="Monitora Teste")
        db.commit()
        assert c.taxonomia_versao == TAXONOMIA_VERSAO and c.pediu_nao_ligar is True


# --------------------------------------------------------------------------- API
def _calls(db, tab, *cats, base=630000, **kw):
    out = []
    for i, cat in enumerate(cats):
        c = Call(id_ligacao=base + i, tabulacao_operador=tab, status="avaliada", categoria=cat,
                 data_ligacao=datetime(2025, 5, 1, 9), **kw)
        db.add(c)
        out.append(c)
    db.commit()
    return out


def test_api_lista_o_catalogo_com_estatisticas_e_liga_ligacoes_antigas(client):
    with SessionLocal() as db:
        _calls(db, "Tabulação Antiga XYZ", "EM_NEGOCIACAO", "EM_NEGOCIACAO", "SEM_INTERESSE", base=631000)
    r = client.get("/api/v1/tabulacoes").json()
    item = next(i for i in r["itens"] if i["nome"] == "Tabulação Antiga XYZ")
    assert item["ligacoes"] == 3 and item["tipo"] == "ignorar" and item["confirmada"] is False
    assert {"tipos", "categorias"} <= set(r["opcoes"])
    assert r["resumo"]["pendentes"] >= 1


def test_api_editar_tabulacao_recalcula_as_ligacoes(client):
    with SessionLocal() as db:
        calls = _calls(db, "PROPOSTA ENVIADA AO BANCO", "EM_NEGOCIACAO", "SEM_INTERESSE", base=632000)
        for c in calls:
            pipeline.atualizar_divergencia(db, c)
        db.commit()
        tab_id = calls[0].tabulacao_id
        assert [c.divergencia_tabulacao for c in calls] == [False, True]  # sugestão: negociação

    r = client.put(f"/api/v1/tabulacoes/{tab_id}", json={"tipo": "resultado", "categorias": ["SEM_INTERESSE"],
                                                        "subcategoria": None, "nao_ligar": False})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["tabulacao"]["confirmada"] is True and body["recalculadas"] == 2 and body["mudaram"] == 2
    with SessionLocal() as db:
        ids = [c.id for c in calls]
        novos = {c.id: c for c in db.scalars(select(Call).where(Call.id.in_(ids)))}
        assert novos[ids[0]].divergencia_tabulacao is True and novos[ids[0]].divergencia_gravidade == "alta"
        assert novos[ids[1]].divergencia_tabulacao is False


def test_api_valida_a_edicao(client):
    with SessionLocal() as db:
        c = _calls(db, "TAB VALIDACAO", "SEM_INTERESSE", base=633000)[0]
        pipeline.atualizar_divergencia(db, c)
        db.commit()
        tab_id = c.tabulacao_id
    ruim = [
        {"tipo": "resultado", "categorias": [], "subcategoria": None, "nao_ligar": False},
        {"tipo": "resultado", "categorias": ["INEXISTENTE"], "subcategoria": None, "nao_ligar": False},
        {"tipo": "resultado", "categorias": ["SEM_INTERESSE"], "subcategoria": "ENGANO_DIRETO", "nao_ligar": False},
        {"tipo": "outro", "categorias": [], "subcategoria": None, "nao_ligar": False},
    ]
    for corpo in ruim:
        assert client.put(f"/api/v1/tabulacoes/{tab_id}", json=corpo).status_code == 422, corpo
    assert client.put("/api/v1/tabulacoes/999999", json=ruim[0] | {"categorias": ["SEM_INTERESSE"]}).status_code == 404


def test_marcar_tabulacao_de_nao_ligar_recalcula_os_pedidos(client):
    with SessionLocal() as db:
        pedido = _calls(db, "CLIENTE NÃO TEM INTERESSE", "SEM_INTERESSE", base=634000, pediu_nao_ligar=True)[0]
        outra = _calls(db, "REGISTRO INTERNO 42", "SEM_INTERESSE", base=634100)[0]
        pipeline.atualizar_divergencia(db, pedido)
        pipeline.atualizar_divergencia(db, outra)
        db.commit()
        tab_optout, pedido_id = outra.tabulacao_id, pedido.id
    r = client.put(f"/api/v1/tabulacoes/{tab_optout}", json={"tipo": "resultado", "categorias": ["SEM_INTERESSE"],
                                                            "subcategoria": None, "nao_ligar": True}).json()
    assert r["mudaram"] >= 1
    with SessionLocal() as db:
        p = db.get(Call, pedido_id)
        assert p.divergencia_tabulacao is True and p.divergencia_gravidade == "alta"


def test_importar_e_exportar_modelo_em_csv(client):
    csv_txt = (
        "tabulacao;tipo;categorias;subcategoria;nao_ligar\n"
        "Cliente pediu retorno;resultado;Em Negociação;Agendamento de retorno;não\n"
        "Bloqueio LGPD;resultado;SEM_INTERESSE|NAO_E_O_CLIENTE;;sim\n"
        "Pausa do sistema;ignorar;;;\n"
        "Linha inválida;resultado;Categoria Que Não Existe;;\n"
    )
    r = client.post("/api/v1/tabulacoes/importar", files={"arquivo": ("modelo.csv", csv_txt.encode("utf-8"), "text/csv")})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["importadas"] == 3 and len(body["erros"]) == 1 and "Linha inválida" in body["erros"][0]
    itens = {i["nome"]: i for i in client.get("/api/v1/tabulacoes").json()["itens"]}
    assert itens["Cliente pediu retorno"]["subcategoria"] == "AGENDAMENTO_RETORNO"
    assert itens["Bloqueio LGPD"]["nao_ligar"] is True and itens["Bloqueio LGPD"]["confirmada"] is True
    assert itens["Pausa do sistema"]["tipo"] == "ignorar"

    exp = client.get("/api/v1/tabulacoes/exportar")
    assert exp.status_code == 200 and "text/csv" in exp.headers["content-type"]
    texto = exp.content.decode("utf-8-sig")
    assert texto.splitlines()[0].startswith("id;id_argus;tabulacao;tipo;categorias")
    assert "Bloqueio LGPD;resultado;SEM_INTERESSE|NAO_E_O_CLIENTE;;sim" in texto


def test_webhook_guarda_o_id_da_tabulacao_e_registra_no_catalogo(client):
    p = {"idTipoWebhook": 2, "idLigacao": 640001, "idTabulacao": 77, "tabulacaoDesc": "Caixa postal operadora"}
    assert client.post("/api/v1/webhooks/argus", json=p).json()["ok"]
    with SessionLocal() as db:
        c = db.scalars(select(Call).where(Call.id_ligacao == 640001)).one()
        assert c.id_tabulacao_argus == 77 and c.tabulacao_id
        assert db.get(Tabulacao, c.tabulacao_id).id_argus == 77


def test_resumo_filtros_e_saude_conhecem_gravidade_e_nao_ligar(client):
    with SessionLocal() as db:
        cs = _calls(db, "EM NEGOCIAÇÃO", "LIGACAO_MUDA", base=650000)
        cs += _calls(db, "CLIENTE NÃO TEM INTERESSE", "SEM_INTERESSE", base=650100, pediu_nao_ligar=True)
        for c in cs:
            pipeline.atualizar_divergencia(db, c)
        db.commit()
        alta_id = cs[0].id
    s = client.get("/api/v1/analytics/summary").json()
    assert set(s["divergencias"]["por_gravidade"]) == {"alta", "media", "baixa"}
    assert s["nao_ligar"] >= 1
    linha = next(m for m in s["matriz_contraste"] if m["tabulacao_operador"] == "EM NEGOCIAÇÃO")
    assert linha["esperadas"] == ["EM_NEGOCIACAO"] and linha["tipo"] == "resultado"

    ids = [i["id"] for i in client.get("/api/v1/calls", params={"gravidade": "alta", "page_size": 500}).json()["items"]]
    assert alta_id in ids
    itens = client.get("/api/v1/calls", params={"nao_ligar": "true", "page_size": 500}).json()["items"]
    assert itens and all(i["pediu_nao_ligar"] for i in itens)
    prim = client.get("/api/v1/calls", params={"divergencia": "true", "ordenar": "gravidade", "page_size": 5}).json()["items"]
    assert prim[0]["divergencia_gravidade"] == "alta"

    saude = client.get("/api/v1/saude").json()
    assert saude["tabulacoes_pendentes"] >= 1
    assert any("tabula" in a["titulo"].lower() for a in saude["alertas"])


def test_ligacao_informa_se_o_significado_da_tabulacao_foi_confirmado(client):
    with SessionLocal() as db:
        c = _calls(db, "TAB CONFIRMACAO", "SEM_INTERESSE", base=660000)[0]
        pipeline.atualizar_divergencia(db, c)
        db.commit()
        cid, tid = c.id, c.tabulacao_id
    assert client.get(f"/api/v1/calls/{cid}").json()["tabulacao_confirmada"] is False
    client.put(f"/api/v1/tabulacoes/{tid}", json={"tipo": "ignorar"})
    assert client.get(f"/api/v1/calls/{cid}").json()["tabulacao_confirmada"] is True
