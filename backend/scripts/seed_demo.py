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
from app.models import Avaliacao, Call, ContactIdentity
from app.services import avaliacoes, pipeline, status

OPERADORES = ["Ana Lima", "Bruno Costa", "Carla Dias", "Diego Rocha", "Elisa Prado", "Fábio Nunes",
              "Gabi Torres", "Hugo Melo", "Íris Campos", "João Reis"]
TRONCOS = ["4NET - PRINCIPAL", "VENDITORE - URA", "TELECOM X - BACKUP"]
GRUPOS = ["EQUIPE COMERCIAL A", "EQUIPE COMERCIAL B", "EQUIPE DIGITAL"]
MONITORAS = ["Monitora Paula", "Monitora Renata"]
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
    base_id = 900_000_000
    with SessionLocal() as db:
        for i in range(n):
            cat, sub, _, tab_ok, falas = rng.choices(CENARIOS, weights=pesos)[0]
            op = rng.choice(OPERADORES)
            nome = rng.choice(NOMES)
            grupo = rng.choice(GRUPOS)
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
        db.commit()
    status.registrar(status.IMPORTACAO, True, f"{n} ligações de demonstração")
    return n


def limpar() -> int:
    with SessionLocal() as db:
        demo = select(Call.id).where(Call.origem == "demo")
        if inspect(db.bind).has_table("ia_uso"):  # banco da versão anterior, com IA
            db.execute(text("DELETE FROM ia_uso WHERE call_id IN (SELECT id FROM calls WHERE origem = 'demo')"))
        db.execute(delete(Avaliacao).where(Avaliacao.call_id.in_(demo)))
        db.execute(delete(ContactIdentity).where(ContactIdentity.id_call_evidencia.in_(demo)))
        db.execute(update(Call).where(Call.ligacao_referencia_id.in_(demo)).values(ligacao_referencia_id=None))
        n = db.execute(delete(Call).where(Call.origem == "demo")).rowcount
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
