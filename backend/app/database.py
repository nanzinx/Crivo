import logging

from sqlalchemy import Boolean, DateTime, create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings

log = logging.getLogger("database")

_db_url = settings.resolved_database_url
_args = {"check_same_thread": False} if _db_url.startswith("sqlite") else {}
engine = create_engine(_db_url, connect_args=_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db(eng: Engine | None = None):
    """Cria tabelas e colunas novas e aplica as migrações de dados pendentes. Não apaga nada."""
    from . import models  # noqa: F401

    eng = eng or engine
    Base.metadata.create_all(eng)

    # Migração simples: cria as colunas novas dos modelos em bancos já existentes (SQLite ou PostgreSQL).
    # Para mudanças além de "adicionar coluna", usar Alembic (roadmap).
    insp = inspect(eng)
    with eng.begin() as conn:
        for table in Base.metadata.sorted_tables:
            existentes = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name not in existentes:
                    tipo = col.type.compile(dialect=eng.dialect)
                    conn.execute(text(f'ALTER TABLE {table.name} ADD COLUMN {col.name} {tipo}'))
    migrar_dados(eng)

    from .services import script  # script de vendas: versão 1 vem da transcrição do PDF

    with Session(eng) as db:
        if script.seed_se_vazio(db):
            db.commit()


# --------------------------------------------------------------------------- migrações de dados
def _colunas(eng: Engine, tabela: str) -> set[str]:
    insp = inspect(eng)
    return {c["name"] for c in insp.get_columns(tabela)} if insp.has_table(tabela) else set()


def _001_monitoria_humana(eng: Engine) -> None:
    """Da versão com IA para a monitoria humana.

    - revisada por humano (revisado_em) -> `avaliada`, com uma avaliação de origem "migrada" (resultado da revisão);
    - resultado só da IA (done, awaiting_ai, erro da IA) -> `pendente_avaliacao`, sem categoria, divergência,
      pedido de não ligar nem marcações de revisão (tudo isso vinha da IA);
    - pending -> `pendente` (ou `pendente_avaliacao`, se o áudio já está no disco); erro de download -> `erro`.

    As colunas de IA (transcrição, confiança, custo...) e a tabela de uso da IA ficam no banco, ocultas.
    Para apagá-las: scripts/limpar_dados_ia.py.
    """
    from . import models
    from .services import pipeline

    cols = _colunas(eng, "calls")
    if "revisado_em" not in cols:  # banco criado já sem IA: nada a migrar
        return
    agora = models.agora()
    tem = lambda c: c in cols  # noqa: E731
    with eng.begin() as conn:
        # 1. revisões humanas viram avaliações finalizadas
        cat_rev = "categoria_revisada" if tem("categoria_revisada") else "NULL"
        sub_rev = "subcategoria_revisada" if tem("subcategoria_revisada") else "NULL"
        revisadas = conn.execute(text(
            f"SELECT id, categoria, subcategoria, {cat_rev} AS cat_rev, {sub_rev} AS sub_rev, revisado_por, "
            "revisado_em, pediu_nao_ligar FROM calls WHERE revisado_em IS NOT NULL AND avaliacao_id IS NULL "
            "ORDER BY id").columns(revisado_em=DateTime, pediu_nao_ligar=Boolean)).all()
        tabela = models.Avaliacao.__table__
        migradas = set()
        for r in revisadas:
            cat = r.cat_rev or r.categoria
            if not cat:
                continue
            sub = r.sub_rev if r.cat_rev else r.subcategoria
            aid = conn.execute(tabela.insert().values(
                call_id=r.id, monitora_nome=(r.revisado_por or "Revisão anterior")[:80], status="finalizada",
                origem="migrada", categoria=cat, subcategoria=sub, pediu_nao_ligar=bool(r.pediu_nao_ligar),
                iniciada_em=r.revisado_em, finalizada_em=r.revisado_em, atualizado_em=agora)).inserted_primary_key[0]
            conn.execute(text("UPDATE calls SET status = 'avaliada', avaliacao_id = :a, categoria = :c, "
                              "subcategoria = :s, erro = NULL WHERE id = :i"), {"a": aid, "c": cat, "s": sub, "i": r.id})
            migradas.add(r.id)

        # 2. o que só a IA tinha decidido volta para a fila de avaliação
        limpar = ["categoria = NULL", "subcategoria = NULL", "divergencia_tabulacao = :f", "divergencia_detalhe = NULL",
                  "divergencia_gravidade = NULL", "pediu_nao_ligar = :f", "conflito_identidade = :f",
                  "ligacao_referencia_id = NULL", "erro = NULL"]
        limpar += [f"{c} = :f" for c in ("precisa_revisao", "na_amostra") if tem(c)]
        limpar += [f"{c} = NULL" for c in ("revisao_motivo",) if tem(c)]
        cond = ("status IN ('done', 'awaiting_ai') OR (status = 'error' AND (erro IS NULL OR erro NOT LIKE 'download:%'))")
        resetar = f"SELECT id FROM calls WHERE {cond}"  # as revisadas já estão como 'avaliada'
        n = conn.execute(text(f"SELECT COUNT(*) FROM ({resetar}) r")).scalar()
        conn.execute(text(f"DELETE FROM contact_identity WHERE id_call_evidencia IN ({resetar})"))
        conn.execute(text(f"UPDATE calls SET conflito_identidade = :f, ligacao_referencia_id = NULL "
                          f"WHERE ligacao_referencia_id IN ({resetar})"), {"f": False})
        conn.execute(text(f"UPDATE calls SET status = 'pendente_avaliacao', {', '.join(limpar)} WHERE {cond}"),
                     {"f": False})

        # 3. download que falhou; ligações que ainda esperam a gravação
        conn.execute(text("UPDATE calls SET status = 'erro' WHERE status = 'error'"))
        conn.execute(text("UPDATE calls SET status = 'pendente_avaliacao' "
                          "WHERE status = 'pending' AND caminho_audio IS NOT NULL"))
        conn.execute(text("UPDATE calls SET status = 'pendente' WHERE status = 'pending'"))
        log.info("migração monitoria humana: %d avaliações migradas, %d ligações voltaram para a fila",
                 len(migradas), n)

    # 4. divergência recalculada pela regra nova (sem IA: só ligações avaliadas contam)
    with Session(bind=eng, autoflush=False, expire_on_commit=False) as db:
        pipeline.vincular_pendentes(db, limite=None)
        pipeline.recalcular(db)


MIGRACOES = [("001_monitoria_humana", _001_monitoria_humana)]


def migrar_dados(eng: Engine | None = None) -> list[str]:
    """Aplica, uma única vez cada, as migrações de dados ainda não registradas em schema_migracoes."""
    from .models import SchemaMigracao

    eng = eng or engine
    aplicadas = []
    with Session(bind=eng) as db:
        feitas = set(db.scalars(text("SELECT nome FROM schema_migracoes")))
    for nome, fn in MIGRACOES:
        if nome in feitas:
            continue
        fn(eng)
        with Session(bind=eng) as db:
            db.add(SchemaMigracao(nome=nome))
            db.commit()
        aplicadas.append(nome)
    return aplicadas
