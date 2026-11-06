from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class Call(Base):
    """Ligação gravada + metadados Argus + qualificação."""

    __tablename__ = "calls"

    id: Mapped[int] = mapped_column(primary_key=True)
    id_ligacao: Mapped[int | None] = mapped_column(Integer, unique=True, index=True)
    nr_lead: Mapped[int | None] = mapped_column(Integer, index=True)
    id_campanha: Mapped[int | None] = mapped_column(Integer, index=True)
    telefone: Mapped[str | None] = mapped_column(String(20), index=True)
    nome_esperado: Mapped[str | None] = mapped_column(String(255), index=True)
    operador_id: Mapped[str | None] = mapped_column(String(64), index=True)
    operador_nome: Mapped[str | None] = mapped_column(String(255))
    tabulacao_operador: Mapped[str | None] = mapped_column(String(255), index=True)

    data_ligacao: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    duracao_segundos: Mapped[float | None] = mapped_column(Float)
    caminho_audio: Mapped[str | None] = mapped_column(Text)
    nome_arquivo: Mapped[str | None] = mapped_column(String(512), unique=True)
    origem: Mapped[str] = mapped_column(String(20), default="local")  # local | argus | csv
    tronco: Mapped[str | None] = mapped_column(String(64), index=True)
    direcionado: Mapped[int | None] = mapped_column(Integer, default=0)
    pre_atendimento: Mapped[bool] = mapped_column(Boolean, default=False)

    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    categoria: Mapped[str | None] = mapped_column(String(40), index=True)
    subcategoria: Mapped[str | None] = mapped_column(String(60), index=True)
    confianca: Mapped[float | None] = mapped_column(Float)
    motor: Mapped[str | None] = mapped_column(String(30))  # gemini | heuristica | csv
    resumo: Mapped[str | None] = mapped_column(Text)
    evidencia: Mapped[str | None] = mapped_column(Text)
    transcricao: Mapped[str | None] = mapped_column(Text)
    transcricao_diarizada: Mapped[list | None] = mapped_column(JSON)
    sentimento_cliente: Mapped[str | None] = mapped_column(String(20))
    metricas_acusticas: Mapped[dict | None] = mapped_column(JSON)
    divergencia_tabulacao: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    divergencia_detalhe: Mapped[str | None] = mapped_column(Text)
    tabulacao_normalizada: Mapped[str | None] = mapped_column(String(64), index=True)
    desligado_por: Mapped[str | None] = mapped_column(String(32), index=True)  # CLIENTE | OPERADOR | OUTRO
    desligamento_detalhe: Mapped[str | None] = mapped_column(String(255))
    tipo_agente: Mapped[str | None] = mapped_column(String(32), index=True)  # COMERCIAL | DIGITAL
    tipo_discagem: Mapped[str | None] = mapped_column(String(32), index=True)  # ATIVO | URA
    grupo_origem: Mapped[str | None] = mapped_column(String(128), index=True)
    tempo_reacao_operador: Mapped[int | None] = mapped_column(Integer)
    cliente_identificado: Mapped[str | None] = mapped_column(String(255))
    conflito_identidade: Mapped[bool] = mapped_column(Boolean, default=False)
    ligacao_referencia_id: Mapped[int | None] = mapped_column(ForeignKey("calls.id"))
    erro: Mapped[str | None] = mapped_column(Text)

    criado_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    qualificado_em: Mapped[datetime | None] = mapped_column(DateTime)

    __table_args__ = (Index("ix_calls_data_cat", "data_ligacao", "categoria"),)


class ContactIdentity(Base):
    """Confirmações positivas de titularidade por telefone (suporta a regra 'É o cliente')."""

    __tablename__ = "contact_identity"

    id: Mapped[int] = mapped_column(primary_key=True)
    telefone: Mapped[str] = mapped_column(String(20), index=True)
    nome_normalizado: Mapped[str] = mapped_column(String(255), index=True)
    id_call_evidencia: Mapped[int] = mapped_column(ForeignKey("calls.id"))
    confirmado_em: Mapped[datetime | None] = mapped_column(DateTime)

    __table_args__ = (Index("ux_contact", "telefone", "nome_normalizado", "id_call_evidencia", unique=True),)
