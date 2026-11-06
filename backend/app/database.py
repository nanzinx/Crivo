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
    from . import models  # noqa: F401

    Base.metadata.create_all(engine)

    # Automatic column migration for sqlite:
    if _db_url.startswith("sqlite"):
        with engine.connect() as conn:
            from sqlalchemy import text
            res = conn.execute(text("PRAGMA table_info(calls)"))
            existing_cols = {row[1] for row in res.fetchall()}

            needed = {
                "tronco": "VARCHAR(64)",
                "direcionado": "INTEGER DEFAULT 0",
                "desligado_por": "VARCHAR(32)",
                "desligamento_detalhe": "VARCHAR(255)",
                "tipo_agente": "VARCHAR(32)",
                "tipo_discagem": "VARCHAR(32)",
                "grupo_origem": "VARCHAR(128)",
                "tabulacao_normalizada": "VARCHAR(64)",
                "divergencia_detalhe": "TEXT",
                "tempo_reacao_operador": "INTEGER",
                "cliente_identificado": "VARCHAR(255)",
            }
            for col_name, col_type in needed.items():
                if col_name not in existing_cols:
                    conn.execute(text(f"ALTER TABLE calls ADD COLUMN {col_name} {col_type}"))
            conn.commit()
