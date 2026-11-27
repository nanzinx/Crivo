"""Gera ligações FICTÍCIAS para demonstrar o painel sem dados reais (nenhum dado pessoal).

Uso (a partir de backend/):
    python -m scripts.seed_demo            # cria ~600 ligações dos últimos 14 dias
    python -m scripts.seed_demo --n 1500   # quantidade personalizada
    python -m scripts.seed_demo --limpar   # remove apenas as ligações de demonstração

As ligações de demonstração ficam com origem="demo" e podem ser apagadas a qualquer momento.
Parte delas já vem avaliada por monitoras fictícias (resultado registrado pela tela); o resto fica na
fila de avaliação, como no dia a dia. Não há dados de IA: o resultado vem só da monitoria humana.
"""
import argparse
import random
from datetime import datetime, timedelta

from sqlalchemy import delete, inspect, select, text, update

from app.database import SessionLocal, init_db
from app.models import (Avaliacao, AvaliacaoCiencia, AvaliacaoEvento, AvaliacaoItem, AvaliacaoMarca, Call,
                        ContactIdentity)
from app.services import avaliacoes, pipeline, ponto, script, status

OPERADORES = ["Ana Lima", "Bruno Costa", "Carla Dias", "Diego Rocha", "Elisa Prado", "Fábio Nunes",
              "Gabi Torres", "Hugo Melo", "Íris Campos", "João Reis"]
TRONCOS = ["4NET - PRINCIPAL", "VENDITORE - URA", "TELECOM X - BACKUP"]
GRUPOS = ["EQUIPE COMERCIAL A", "EQUIPE COMERCIAL B", "EQUIPE DIGITAL"]
MONITORAS = ["Monitora Paula", "Monitora Renata"]
SUPERVISORES = ["Supervisora Ana", "Supervisor Bruno"]
NOMES = ["Maria Souza", "José Almeida", "Antônia Ferreira", "Francisco Gomes", "Luzia Martins",
         "Raimundo Barbosa", "Rita Cardoso", "Sebastião Ribeiro", "Tereza Moura", "Valdir Pinto"]

# (categoria, subcategoria, peso, tabulação "correta" do operador, falas de exemplo: só para o pedido de não ligar)
CENARIOS = [
    ("EM_NEGOCIACAO", "PROPOSTA_EM_ANDAMENTO", 9, "EM NEGOCIAÇÃO",
     [("ATENDENTE", "Bom dia, falo com a dona {nome}? Tenho uma proposta de portabilidade com parcela menor."),
      ("CLIENTE", "Sou eu sim. Quanto ficaria a parcela?"),
      ("ATENDENTE", "Ficaria em torno de 280 reais, reduzindo a taxa atual.")]),
    ("EM_NEGOCIACAO", "MIGRACAO_WHATSAPP", 4, "EM NEGOCIAÇÃO",
     [("ATENDENTE", "Posso te enviar a simulação?"), ("CLIENTE", "Manda pelo WhatsApp que eu vejo com calma.")]),
    ("EM_NEGOCIACAO", "AGENDAMENTO_RETORNO", 3, "RETORNO AGENDADO",
     [("CLIENTE", "Agora não posso, me liga depois das seis?"), ("ATENDENTE", "Combinado, retorno às 18h.")]),
    ("NAO_E_O_CLIENTE", "ENGANO_DIRETO", 10, "NÃO É O CLIENTE",
     [("ATENDENTE", "Falo com o senhor {nome}?"), ("CLIENTE", "Não conheço ninguém com esse nome, é engano.")]),
    ("NAO_E_O_CLIENTE", "TERCEIRO_FAMILIA", 6, "NÃO É O CLIENTE",
     [("CLIENTE", "Ela é minha mãe, só chega à noite."), ("ATENDENTE", "Obrigado, retorno mais tarde.")]),
    ("NAO_E_O_CLIENTE", "CHIP_NOVO", 3, "NÃO É O CLIENTE",
     [("CLIENTE", "Esse número é novo, comprei o chip mês passado.")]),
    ("SEM_INTERESSE", "CLIENTE_CALMO", 12, "CLIENTE NÃO TEM INTERESSE",
     [("ATENDENTE", "Temos uma condição especial de crédito."), ("CLIENTE", "Não tenho interesse, obrigado.")]),
    ("SEM_INTERESSE", "CLIENTE_REVOLTADO", 4, "NÃO LIGAR / BLOQUEIO",
     [("CLIENTE", "Pare de ligar! Todo dia isso, que saco.")]),
    ("SEM_INTERESSE", "JA_E_CLIENTE", 2, "CLIENTE NÃO TEM INTERESSE",
     [("CLIENTE", "Eu já sou cliente de vocês, já fiz contrato ano passado.")]),
    ("LIGACAO_MUDA", "DESLIGOU_NA_ABERTURA", 4, "LIGAÇÃO MUDA / CAIXA POSTAL",
     [("CLIENTE", "Alô?"), ("ATENDENTE", "Bom dia, aqui é da…")]),
    ("SEM_INTERESSE", "CLIENTE_CALMO", 2, "AGENDAMENTO AUTOMÁTICO DISCADOR",
     [("CLIENTE", "Não tenho interesse, obrigado.")]),
    ("SEM_INTERESSE", "JA_POSSUI", 3, "CLIENTE NÃO TEM INTERESSE",
     [("CLIENTE", "Já fiz portabilidade semana passada, não tenho margem.")]),
    ("LIGACAO_MUDA", "ATENDENTE_SOLITARIO", 14, "LIGAÇÃO MUDA / CAIXA POSTAL",
     [("ATENDENTE", "Alô? Bom dia? Alô?")]),
    ("LIGACAO_MUDA", "MUDO_TOTAL", 7, "LIGAÇÃO MUDA / CAIXA POSTAL", []),
    ("LIGACAO_MUDA", "FALHA_COMUNICACAO", 3, "LIGAÇÃO MUDA / CAIXA POSTAL",
     [("CLIENTE", "Alô? Não estou ouvindo."), ("ATENDENTE", "Alô? A senhora me escuta?")]),
    ("CAIXA_POSTAL", "URA_OPERADORA", 12, "LIGAÇÃO MUDA / CAIXA POSTAL",
     [("URA", "Deixe sua mensagem após o sinal.")]),
    ("CAIXA_POSTAL", "NUMERO_INEXISTENTE", 4, "LIGAÇÃO MUDA / CAIXA POSTAL",
     [("URA", "Este número de telefone não existe.")]),
    ("INDETERMINADO", "SEM_DADOS", 2, "TEMPO PÓS ATENDIMENTO", [("ATENDENTE", "...")]),
]
# tabulações que o operador escolhe quando erra (gera divergência realista)
TABULACOES_ERRADAS = ["CLIENTE NÃO TEM INTERESSE", "LIGAÇÃO MUDA / CAIXA POSTAL", "TEMPO PÓS ATENDIMENTO",
                      "NÃO É O CLIENTE"]


def _hora_util(rng: random.Random, dia: datetime) -> datetime:
    hora = min(19, max(8, int(rng.gauss(13, 3))))
    return dia.replace(hour=hora, minute=rng.randint(0, 59), second=rng.randint(0, 59), microsecond=0)


def gerar(n: int, seed: int = 42) -> int:
    rng = random.Random(seed)
    init_db()
    hoje = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    pesos = [c[2] for c in CENARIOS]
    # cada operador tem uma "propensão a errar" diferente, para o ranking ficar interessante
    erro_op = {op: rng.uniform(0.03, 0.35) for op in OPERADORES}
    equipe_op = {op: GRUPOS[i % len(GRUPOS)] for i, op in enumerate(OPERADORES)}  # cada operador numa equipe
    base_id = 900_000_000
    with SessionLocal() as db:
        v = script.ativo(db)
        roteiro = [(i, sec) for sec, itens in script.secoes_e_itens(db, v.id) for i in itens] if v else []
        for i in range(n):
            cat, sub, _, tab_ok, falas = rng.choices(CENARIOS, weights=pesos)[0]
            op = rng.choice(OPERADORES)
            nome = rng.choice(NOMES)
            grupo = equipe_op[op]
            tronco = rng.choices(TRONCOS, weights=[6, 3, 1])[0]
            if tronco.startswith("TELECOM") and rng.random() < 0.5:  # tronco "ruim": mais ligações mudas
                cat, sub, tab_ok, falas = "LIGACAO_MUDA", "MUDO_TOTAL", "LIGAÇÃO MUDA / CAIXA POSTAL", []
            tab = rng.choice(TABULACOES_ERRADAS) if rng.random() < erro_op[op] else tab_ok
            if tab_ok == "NÃO LIGAR / BLOQUEIO" and rng.random() < 0.5:
                tab = "CLIENTE NÃO TEM INTERESSE"  # pedido de não ligar sem registro (LGPD)
            dur = {"LIGACAO_MUDA": rng.uniform(3, 15), "CAIXA_POSTAL": rng.uniform(8, 25)}.get(cat, rng.uniform(20, 240))
            dia = hoje - timedelta(days=rng.randint(0, 13))
            r = rng.random()
            # as ligações mais antigas já foram quase todas avaliadas; as de hoje e ontem, menos
            p_avaliada = 0.25 if dia >= hoje - timedelta(days=1) else 0.7
            if r < p_avaliada:
                st = "avaliada" if rng.random() < 0.96 else "nao_avaliavel"
            else:
                r2 = rng.random()
                st = "pendente_avaliacao" if r2 < 0.88 else ("pendente" if r2 < 0.95 else "erro")
            c = Call(
                id_ligacao=base_id + i, nr_lead=rng.randint(100000, 999999), id_campanha=rng.choice([12, 15]),
                telefone=f"119{rng.randint(10000000, 99999999)}", nome_esperado=nome, operador_nome=op,
                operador_id=str(1000 + OPERADORES.index(op)), tabulacao_operador=tab, tronco=tronco,
                grupo_origem=grupo, tipo_agente="DIGITAL" if "DIGITAL" in grupo else "COMERCIAL",
                tipo_discagem="URA" if "URA" in tronco else "ATIVO",
                desligado_por=rng.choices(["CLIENTE", "OPERADOR", "OUTRO"], weights=[6, 3, 1])[0],
                tempo_reacao_operador=rng.randint(1, 9), data_ligacao=_hora_util(rng, dia),
                duracao_segundos=round(dur, 1), origem="demo",
                status="pendente_avaliacao" if st in ("avaliada", "nao_avaliavel") else st,
            )
            c.desligamento_detalhe = {"CLIENTE": "Atendimento: BYE recebido.", "OPERADOR": "Atendimento: BYE enviado.",
                                      "OUTRO": "CANCEL / timeout"}[c.desligado_por]
            if st == "erro":
                c.erro = "download: gravação ainda não disponível (demonstração)"
            db.add(c)
            db.flush()
            pipeline.atualizar_divergencia(db, c)  # registra a tabulação no catálogo
            if st in ("avaliada", "nao_avaliavel"):
                pediu = any("pare de ligar" in t.lower() for _, t in falas)
                a = avaliacoes.registrar_resultado(
                    db, c, cat, sub, pediu_nao_ligar=pediu, nao_avaliavel=st == "nao_avaliavel",
                    motivo="Áudio cortado no meio da conversa (demonstração).", monitora_nome=rng.choice(MONITORAS))
                a.iniciada_em = c.data_ligacao + timedelta(hours=rng.randint(1, 20))
                a.finalizada_em = a.atualizado_em = a.iniciada_em + timedelta(minutes=rng.randint(2, 9))
                if st == "avaliada" and cat in ("EM_NEGOCIACAO", "SEM_INTERESSE") and roteiro:
                    _avaliar_script(db, rng, a, roteiro, "venda" if sub == "ACEITE_VERBAL" else "recusa"
                                    if cat == "SEM_INTERESSE" else "outro", erro_op[op], dia < hoje - timedelta(days=3))
        db.commit()
    with SessionLocal() as db:
        _ponto_demo(db, rng, hoje.date())
        db.commit()
    status.registrar(status.IMPORTACAO, True, f"{n} ligações de demonstração")
    return n


FEEDBACKS = [("Boa abertura, tom de voz seguro", "Explicar a portabilidade com o exemplo do celular"),
             ("Apresentou bem a proposta", "Confirmar a conta antes de encerrar"),
             ("Tratou a objeção com calma", "Perguntar o que impede de fechar hoje"),
             ("Seguiu o script do início ao fim", "Reforçar que a parcela continua igual")]


def _avaliar_script(db, rng, a, roteiro, desfecho, taxa_erro, com_ciencia):
    """Avaliação de script fictícia: operadores com mais erro de tabulação também erram mais o script."""
    a.script_versao_id, a.desfecho = roteiro[0][1].versao_id, desfecho
    for item, sec in roteiro:
        if not avaliacoes.secao_aplica(sec.aplicabilidade, desfecho):
            continue
        r = rng.random()
        estado = ("errou" if r < taxa_erro * 0.8 else "divergencia" if r < taxa_erro * 1.3
                  else "nao_se_aplica" if r < taxa_erro * 1.3 + 0.03 else "acertou")
        if item.critico and estado == "errou" and rng.random() < 0.6:
            estado = "acertou"  # falha crítica é rara
        db.add(AvaliacaoItem(avaliacao_id=a.id, item_id=item.id, estado=estado,
                             comentario="Falou diferente do script (demonstração)." if estado in ("errou", "divergencia") else None))
        if estado != "acertou" or rng.random() < 0.15:
            db.add(AvaliacaoMarca(avaliacao_id=a.id, item_id=item.id, tipo=estado if estado != "nao_se_aplica" else "nota",
                                  segundos=round(rng.uniform(2, 200), 1)))
    db.flush()
    calc = avaliacoes.calcular(db, a)
    a.nota, a.falha_critica = calc["nota"], calc["falha_critica"]
    a.feedback_fortes, a.feedback_melhorar = rng.choice(FEEDBACKS)
    if com_ciencia and rng.random() < 0.7:
        db.add(AvaliacaoCiencia(avaliacao_id=a.id, usuario_nome=rng.choice(SUPERVISORES),
                                em=a.finalizada_em + timedelta(days=1), devolutiva="Conversado no 1:1 (demonstração)."))


PAUSAS_DEMO = [("NOVO LEAD", 3, 60), ("PESQUISANDO LEAD", 20, 240), ("LIGAÇÃO - WPP", 60, 600), ("Banheiro", 60, 420),
               ("Feedback", 60, 300)]


def _ponto_demo(db, rng, hoje):
    """Ponto fictício dos operadores da demonstração (5 dias úteis), importado como os CSVs do Argus."""
    from app.models import PontoGrupo

    for g in GRUPOS:
        row = db.get(PontoGrupo, g) or PontoGrupo(grupo=g)
        row.incluir, row.tolerancia_min = True, 10
        row.entrada_prevista = "08:30;14:00" if "DIGITAL" in g else "10:00"
        db.add(row)
    db.flush()
    equipe_op = {op: GRUPOS[i % len(GRUPOS)] for i, op in enumerate(OPERADORES)}
    atrasa = {op: rng.random() < 0.25 for op in OPERADORES}  # alguns operadores costumam atrasar
    dias = [hoje - timedelta(days=k) for k in range(8) if (hoje - timedelta(days=k)).weekday() < 6][:5]
    for dia in sorted(dias):
        ponto_csv = ['"Data";"Grupo Atual";"Operador";"Entrada";"Saída"']
        pausas_csv = ['" ";"Grupo Operacional";"Operador";"Descrição da Pausa";"Inicio";"Fim";"Tempo"']
        for op in OPERADORES:
            g = equipe_op[op]
            base = (14 * 60 if OPERADORES.index(op) % 2 else 8 * 60 + 30) if "DIGITAL" in g else 10 * 60  # turnos da equipe
            ent = base + (rng.randint(12, 35) if atrasa[op] and rng.random() < 0.6 else rng.randint(-9, 6))
            sai = ent + 7 * 60 + rng.randint(-5, 10)
            fmt = lambda m: f"{m // 60:02d}:{m % 60:02d}"  # noqa: E731
            ponto_csv.append(f'"{dia.isoformat()}";"{g}";"{op}";"{fmt(ent)}";"{fmt(sai) if dia < hoje else ""}"')
            if dia == hoje:
                continue
            t = datetime.combine(dia, datetime.min.time()) + timedelta(minutes=ent + 20)
            almoco_ini = datetime.combine(dia, datetime.min.time()) + timedelta(minutes=ent + 180 + rng.randint(0, 40))
            almoco_seg = rng.randint(40, 58) * 60 if rng.random() < 0.85 else rng.randint(62, 80) * 60
            pausas = [("Almoço", almoco_ini, almoco_seg)]
            while t < almoco_ini + timedelta(hours=3):
                desc, mn, mx = rng.choice(PAUSAS_DEMO)
                seg = rng.randint(mn, mx)
                pausas.append((desc, t, seg))
                t += timedelta(seconds=seg + rng.randint(300, 1500))
            for desc, ini, seg in pausas:
                fim = ini + timedelta(seconds=seg)
                f2 = lambda d: d.strftime("%d/%m/%Y %H:%M:%S")  # noqa: E731
                pausas_csv.append(f'"";"{g}";"{op}";"{desc}";"{f2(ini)}";"{f2(fim)}";"{seg // 3600:02d}:{seg // 60 % 60:02d}:{seg % 60:02d}"')
        ponto.importar(db, f"ENTRADA-SAIDA-{dia.isoformat()}.csv", "\r\n".join(ponto_csv).encode("cp1252"), "Demonstração")
        if dia < hoje:
            ponto.importar(db, f"PAUSAS-{dia.isoformat()}.csv", "\r\n".join(pausas_csv).encode("cp1252"), "Demonstração")


def limpar() -> int:
    with SessionLocal() as db:
        demo = select(Call.id).where(Call.origem == "demo")
        if inspect(db.bind).has_table("ia_uso"):  # banco da versão anterior, com IA
            db.execute(text("DELETE FROM ia_uso WHERE call_id IN (SELECT id FROM calls WHERE origem = 'demo')"))
        avs = select(Avaliacao.id).where(Avaliacao.call_id.in_(demo))
        for t in (AvaliacaoItem, AvaliacaoMarca, AvaliacaoEvento, AvaliacaoCiencia):
            db.execute(delete(t).where(t.avaliacao_id.in_(avs)))
        db.execute(update(Call).where(Call.origem == "demo").values(avaliacao_id=None))
        db.execute(delete(Avaliacao).where(Avaliacao.call_id.in_(demo)))
        db.execute(delete(ContactIdentity).where(ContactIdentity.id_call_evidencia.in_(demo)))
        db.execute(update(Call).where(Call.ligacao_referencia_id.in_(demo)).values(ligacao_referencia_id=None))
        n = db.execute(delete(Call).where(Call.origem == "demo")).rowcount
        from app.models import Operador, PontoImportacao, PontoJornada, PontoPausa

        imps = select(PontoImportacao.id).where(PontoImportacao.importado_por == "Demonstração")
        db.execute(delete(PontoJornada).where(PontoJornada.importacao_id.in_(imps)))
        db.execute(delete(PontoPausa).where(PontoPausa.importacao_id.in_(imps)))
        db.execute(delete(PontoImportacao).where(PontoImportacao.importado_por == "Demonstração"))
        db.execute(delete(Operador).where(Operador.nome.in_(OPERADORES)))
        db.commit()
    return n


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n", type=int, default=600)
    ap.add_argument("--limpar", action="store_true")
    a = ap.parse_args()
    if a.limpar:
        print(f"{limpar()} ligações de demonstração removidas.")
    else:
        print(f"{gerar(a.n)} ligações de demonstração criadas (origem='demo').")
