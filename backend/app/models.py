from datetime import date, datetime


def agora() -> datetime:
    """Horário local do servidor (mesma referência das datas do Argus). Configure TZ=America/Sao_Paulo."""
    return datetime.now()

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text
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
    id_tabulacao_argus: Mapped[int | None] = mapped_column(Integer, index=True)
    tabulacao_id: Mapped[int | None] = mapped_column(ForeignKey("tabulacoes.id"), index=True)  # modelo de tabulação

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
    motor: Mapped[str | None] = mapped_column(String(30))  # openai | heuristica | csv | html
    resumo: Mapped[str | None] = mapped_column(Text)
    evidencia: Mapped[str | None] = mapped_column(Text)
    transcricao: Mapped[str | None] = mapped_column(Text)
    transcricao_diarizada: Mapped[list | None] = mapped_column(JSON)
    sentimento_cliente: Mapped[str | None] = mapped_column(String(20))
    metricas_acusticas: Mapped[dict | None] = mapped_column(JSON)
    divergencia_tabulacao: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    divergencia_detalhe: Mapped[str | None] = mapped_column(Text)
    divergencia_gravidade: Mapped[str | None] = mapped_column(String(10), index=True)  # alta | media | baixa
    pediu_nao_ligar: Mapped[bool | None] = mapped_column(Boolean, default=False, index=True)  # LGPD
    taxonomia_versao: Mapped[int | None] = mapped_column(Integer)
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

    # Resposta original da IA (preservada mesmo depois de uma revisão humana mudar `categoria`)
    categoria_ia: Mapped[str | None] = mapped_column(String(40), index=True)
    subcategoria_ia: Mapped[str | None] = mapped_column(String(60))
    # Revisão humana feita pela tela (ou escuta manual importada): é o gabarito para medir a IA
    categoria_revisada: Mapped[str | None] = mapped_column(String(40))
    subcategoria_revisada: Mapped[str | None] = mapped_column(String(60))
    revisado_por: Mapped[str | None] = mapped_column(String(80))
    revisado_em: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    revisao_observacao: Mapped[str | None] = mapped_column(Text)
    na_amostra: Mapped[bool | None] = mapped_column(Boolean, default=False, index=True)  # sorteada p/ revisão

    # Revisão humana: a IA não teve segurança, ou o áudio contradiz a tabulação
    precisa_revisao: Mapped[bool | None] = mapped_column(Boolean, default=False, index=True)
    revisao_motivo: Mapped[str | None] = mapped_column(String(255))
    fala_segundos: Mapped[float | None] = mapped_column(Float)  # fala detectada localmente (VAD)
    custo_usd: Mapped[float | None] = mapped_column(Float, default=0)  # gasto acumulado de IA nesta ligação

    criado_em: Mapped[datetime] = mapped_column(DateTime, default=agora)
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


class SystemStatus(Base):
    """Último resultado de cada integração (webhook, polling, IA, download) para o painel de saúde."""

    __tablename__ = "system_status"

    chave: Mapped[str] = mapped_column(String(64), primary_key=True)
    ok: Mapped[bool] = mapped_column(Boolean, default=True)
    em: Mapped[datetime] = mapped_column(DateTime, default=agora)
    detalhe: Mapped[str | None] = mapped_column(Text)
    ultimo_sucesso_em: Mapped[datetime | None] = mapped_column(DateTime)
    ultima_falha_em: Mapped[datetime | None] = mapped_column(DateTime)


class IaUso(Base):
    """Cada chamada paga de IA (transcrição ou classificação). Base do painel de custo."""

    __tablename__ = "ia_uso"

    id: Mapped[int] = mapped_column(primary_key=True)
    call_id: Mapped[int | None] = mapped_column(ForeignKey("calls.id"), index=True)
    em: Mapped[datetime] = mapped_column(DateTime, default=agora, index=True)
    tipo: Mapped[str] = mapped_column(String(20))  # transcricao | classificacao
    modelo: Mapped[str] = mapped_column(String(64))
    audio_segundos: Mapped[float] = mapped_column(Float, default=0)  # duração enviada (paga)
    audio_segundos_original: Mapped[float | None] = mapped_column(Float)  # duração da gravação, antes do corte
    tokens_entrada: Mapped[int] = mapped_column(Integer, default=0)
    tokens_saida: Mapped[int] = mapped_column(Integer, default=0)
    custo_usd: Mapped[float] = mapped_column(Float, default=0)


class Tabulacao(Base):
    """Modelo de tabulação: o que cada tabulação do Argus significa na taxonomia do Crivo.

    Toda tabulação nova que aparece entra aqui com um significado SUGERIDO (pelo texto). A equipe
    confirma ou corrige na tela "Modelo de tabulação"; a divergência passa a usar a regra confirmada.
    """

    __tablename__ = "tabulacoes"

    id: Mapped[int] = mapped_column(primary_key=True)
    chave: Mapped[str] = mapped_column(String(255), unique=True, index=True)  # texto normalizado
    nome: Mapped[str] = mapped_column(String(255))  # texto como aparece no Argus
    id_argus: Mapped[int | None] = mapped_column(Integer, index=True)
    tipo: Mapped[str] = mapped_column(String(20), default="resultado")  # resultado | nao_tabulado | ignorar
    categorias: Mapped[list | None] = mapped_column(JSON)  # categorias da IA aceitas como coerentes
    subcategoria: Mapped[str | None] = mapped_column(String(60))  # opcional: exige também a subcategoria
    nao_ligar: Mapped[bool] = mapped_column(Boolean, default=False)  # esta tabulação registra o pedido de não ligar
    confirmada: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=agora)
    atualizado_em: Mapped[datetime | None] = mapped_column(DateTime)


class Alerta(Base):
    """Alerta de negócio (operador, tronco, LGPD) ou de sistema. Fica aberto enquanto a condição durar."""

    __tablename__ = "alertas"

    id: Mapped[int] = mapped_column(primary_key=True)
    chave: Mapped[str] = mapped_column(String(160), index=True)  # identifica a condição (ex.: "operador:Ana")
    tipo: Mapped[str] = mapped_column(String(30))  # operador | tronco | nao_ligar | sistema
    nivel: Mapped[str] = mapped_column(String(10))  # critico | atencao
    titulo: Mapped[str] = mapped_column(String(160))
    mensagem: Mapped[str] = mapped_column(Text)
    link: Mapped[str | None] = mapped_column(String(500))  # caminho no painel com os filtros do caso
    valor: Mapped[float | None] = mapped_column(Float)
    aberto_em: Mapped[datetime] = mapped_column(DateTime, default=agora, index=True)
    atualizado_em: Mapped[datetime] = mapped_column(DateTime, default=agora)
    resolvido_em: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    notificado_em: Mapped[datetime | None] = mapped_column(DateTime)
    reconhecido_por: Mapped[str | None] = mapped_column(String(80))
    reconhecido_em: Mapped[datetime | None] = mapped_column(DateTime)


class Relatorio(Base):
    """Relatório diário (um por dia; gerar de novo substitui)."""

    __tablename__ = "relatorios"

    id: Mapped[int] = mapped_column(primary_key=True)
    data: Mapped[date] = mapped_column(Date, unique=True, index=True)
    gerado_em: Mapped[datetime] = mapped_column(DateTime, default=agora)
    dados: Mapped[dict] = mapped_column(JSON)
    texto: Mapped[str] = mapped_column(Text)
    enviado_em: Mapped[datetime | None] = mapped_column(DateTime)
    envio_detalhe: Mapped[str | None] = mapped_column(Text)
