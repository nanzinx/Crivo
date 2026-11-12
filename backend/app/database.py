from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings

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


def init_db():
    from sqlalchemy import inspect, text

    from . import models  # noqa: F401

    Base.metadata.create_all(engine)

    # Migração simples: cria as colunas novas dos modelos em bancos já existentes (SQLite ou PostgreSQL).
    # Para mudanças além de "adicionar coluna", usar Alembic (roadmap).
    insp = inspect(engine)
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            existentes = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name not in existentes:
                    tipo = col.type.compile(dialect=engine.dialect)
                    conn.execute(text(f'ALTER TABLE {table.name} ADD COLUMN {col.name} {tipo}'))
