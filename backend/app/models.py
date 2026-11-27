from datetime import date, datetime


def agora() -> datetime:
    """Horário local do servidor (mesma referência das datas do Argus). Configure TZ=America/Sao_Paulo."""
    return datetime.now()

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class Call(Base):
    """Ligação gravada + metadados Argus + resultado da avaliação da monitora."""

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

    # Ciclo de vida: pendente (aguardando o áudio) -> pendente_avaliacao -> em_avaliacao -> avaliada | nao_avaliavel;
    # erro = falha no download da gravação. Ver services/avaliacoes.py.
    status: Mapped[str] = mapped_column(String(20), default="pendente", index=True)
    # Resultado da ligação: cópia do que a monitora registrou na avaliação finalizada (avaliacao_id)
    categoria: Mapped[str | None] = mapped_column(String(40), index=True)
    subcategoria: Mapped[str | None] = mapped_column(String(60), index=True)
    avaliacao_id: Mapped[int | None] = mapped_column(Integer, index=True)  # avaliação vigente (tabela avaliacoes)
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

    # Colunas da versão anterior, com IA (confiança, motor, resumo, transcrição, custo...), continuam
    # no banco antigo, mas saíram do código: ver database.migrar_dados e scripts/limpar_dados_ia.py.

    criado_em: Mapped[datetime] = mapped_column(DateTime, default=agora)

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
    """Último resultado de cada integração (webhook, polling, download) para o painel de saúde."""

    __tablename__ = "system_status"

    chave: Mapped[str] = mapped_column(String(64), primary_key=True)
    ok: Mapped[bool] = mapped_column(Boolean, default=True)
    em: Mapped[datetime] = mapped_column(DateTime, default=agora)
    detalhe: Mapped[str | None] = mapped_column(Text)
    ultimo_sucesso_em: Mapped[datetime | None] = mapped_column(DateTime)
    ultima_falha_em: Mapped[datetime | None] = mapped_column(DateTime)


class Avaliacao(Base):
    """Avaliação de uma ligação pela monitora de qualidade. Dela vem o resultado da ligação.

    origem: tela (registrada no painel) | importada (escuta manual em CSV/HTML) | migrada (revisão humana
    da versão anterior, com IA).
    """

    __tablename__ = "avaliacoes"

    id: Mapped[int] = mapped_column(primary_key=True)
    call_id: Mapped[int] = mapped_column(ForeignKey("calls.id"), index=True)
    monitora_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), index=True)
    monitora_nome: Mapped[str | None] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(20), default="rascunho", index=True)  # rascunho | finalizada | nao_avaliavel
    origem: Mapped[str] = mapped_column(String(20), default="tela")  # tela | importada | migrada
    categoria: Mapped[str | None] = mapped_column(String(40))
    subcategoria: Mapped[str | None] = mapped_column(String(60))
    pediu_nao_ligar: Mapped[bool] = mapped_column(Boolean, default=False)
    nao_avaliavel_motivo: Mapped[str | None] = mapped_column(Text)
    iniciada_em: Mapped[datetime] = mapped_column(DateTime, default=agora)
    finalizada_em: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    atualizado_em: Mapped[datetime | None] = mapped_column(DateTime)
    # avaliação do script (fase 2). Sem script_versao_id = registro rápido, só o resultado da ligação.
    script_versao_id: Mapped[int | None] = mapped_column(ForeignKey("script_versoes.id"), index=True)
    desfecho: Mapped[str | None] = mapped_column(String(20))  # venda | recusa | outro | sem_conversa
    observacao: Mapped[str | None] = mapped_column(Text)
    feedback_fortes: Mapped[str | None] = mapped_column(Text)
    feedback_melhorar: Mapped[str | None] = mapped_column(Text)
    nota: Mapped[float | None] = mapped_column(Float)  # 0 a 100
    falha_critica: Mapped[bool] = mapped_column(Boolean, default=False)
    # trava: uma monitora por vez; expira sozinha (o autosave renova)
    trava_usuario_id: Mapped[int | None] = mapped_column(Integer)
    trava_nome: Mapped[str | None] = mapped_column(String(80))
    trava_ate: Mapped[datetime | None] = mapped_column(DateTime)


class ScriptVersao(Base):
    """Versão do script de vendas. Só uma fica ativa; a avaliação guarda a versão com que foi feita.

    status: rascunho (editável) | ativa | arquivada. Versão já usada em avaliação não muda mais.
    """

    __tablename__ = "script_versoes"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(120))
    numero: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(20), default="rascunho", index=True)
    valor_divergencia: Mapped[float] = mapped_column(Float, default=0.5)  # quanto vale um item "com divergência"
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=agora)
    criado_por: Mapped[str | None] = mapped_column(String(80))
    publicada_em: Mapped[datetime | None] = mapped_column(DateTime)


class ScriptSecao(Base):
    """Bloco do script. aplicabilidade: sempre | venda (só se houve venda) | recusa (só se houve recusa)."""

    __tablename__ = "script_secoes"

    id: Mapped[int] = mapped_column(primary_key=True)
    versao_id: Mapped[int] = mapped_column(ForeignKey("script_versoes.id"), index=True)
    ordem: Mapped[int] = mapped_column(Integer, default=0)
    titulo: Mapped[str] = mapped_column(String(160))
    aplicabilidade: Mapped[str] = mapped_column(String(20), default="sempre")
    orientacao: Mapped[str | None] = mapped_column(Text)


class ScriptItem(Base):
    """Trecho marcável do script (acertou / errou / divergência / não se aplica)."""

    __tablename__ = "script_itens"

    id: Mapped[int] = mapped_column(primary_key=True)
    secao_id: Mapped[int] = mapped_column(ForeignKey("script_secoes.id"), index=True)
    ordem: Mapped[int] = mapped_column(Integer, default=0)
    texto: Mapped[str] = mapped_column(Text)
    orientacao: Mapped[str | None] = mapped_column(Text)
    peso: Mapped[float] = mapped_column(Float, default=1.0)
    critico: Mapped[bool] = mapped_column(Boolean, default=False)


class AvaliacaoItem(Base):
    """Marcação de um item do script numa avaliação."""

    __tablename__ = "avaliacao_itens"
    __table_args__ = (UniqueConstraint("avaliacao_id", "item_id", name="uq_avaliacao_item"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    avaliacao_id: Mapped[int] = mapped_column(ForeignKey("avaliacoes.id"), index=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("script_itens.id"))
    estado: Mapped[str | None] = mapped_column(String(20))  # acertou | errou | divergencia | nao_se_aplica
    comentario: Mapped[str | None] = mapped_column(Text)


class AvaliacaoMarca(Base):
    """Marcador no áudio: um momento da gravação, ligado (ou não) a um item do script."""

    __tablename__ = "avaliacao_marcas"

    id: Mapped[int] = mapped_column(primary_key=True)
    avaliacao_id: Mapped[int] = mapped_column(ForeignKey("avaliacoes.id"), index=True)
    item_id: Mapped[int | None] = mapped_column(ForeignKey("script_itens.id"))
    segundos: Mapped[float] = mapped_column(Float)
    tipo: Mapped[str] = mapped_column(String(20), default="nota")  # acertou | errou | divergencia | nota
    texto: Mapped[str | None] = mapped_column(Text)


class AvaliacaoEvento(Base):
    """Auditoria da avaliação: início, finalização, reabertura (com o que era antes), trava liberada..."""

    __tablename__ = "avaliacao_eventos"

    id: Mapped[int] = mapped_column(primary_key=True)
    avaliacao_id: Mapped[int] = mapped_column(ForeignKey("avaliacoes.id"), index=True)
    em: Mapped[datetime] = mapped_column(DateTime, default=agora)
    usuario_id: Mapped[int | None] = mapped_column(Integer)
    usuario_nome: Mapped[str | None] = mapped_column(String(80))
    acao: Mapped[str] = mapped_column(String(30))
    detalhe: Mapped[dict | None] = mapped_column(JSON)


class Parametro(Base):
    """Parâmetros da operação editáveis na tela (ex.: meta diária de avaliações por monitora)."""

    __tablename__ = "parametros"

    chave: Mapped[str] = mapped_column(String(60), primary_key=True)
    valor: Mapped[str] = mapped_column(String(200))
    atualizado_em: Mapped[datetime | None] = mapped_column(DateTime)


class SchemaMigracao(Base):
    """Migrações de dados já aplicadas (database.migrar_dados): cada uma roda uma única vez."""

    __tablename__ = "schema_migracoes"

    nome: Mapped[str] = mapped_column(String(80), primary_key=True)
    aplicada_em: Mapped[datetime] = mapped_column(DateTime, default=agora)


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
    categorias: Mapped[list | None] = mapped_column(JSON)  # categorias do resultado aceitas como coerentes
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
    tipo: Mapped[str] = mapped_column(String(30))  # operador | tronco | nao_ligar | sistema | aderencia | falha_critica | atraso | almoco
    grupo: Mapped[str | None] = mapped_column(String(128), index=True)  # equipe (supervisor vê só as dele); None = geral
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


class Usuario(Base):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    nome: Mapped[str] = mapped_column(String(80))
    senha_hash: Mapped[str] = mapped_column(String(255))
    papel: Mapped[str] = mapped_column(String(20), default="supervisor")  # admin | supervisor | monitora | leitura
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=agora)
    ultimo_login_em: Mapped[datetime | None] = mapped_column(DateTime)
    falhas_login: Mapped[int] = mapped_column(Integer, default=0)
    bloqueado_ate: Mapped[datetime | None] = mapped_column(DateTime)


class Sessao(Base):
    """Sessão de login. Só o hash do token fica no banco: um vazamento do banco não dá acesso."""

    __tablename__ = "sessoes"

    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), index=True)
    criada_em: Mapped[datetime] = mapped_column(DateTime, default=agora)
    expira_em: Mapped[datetime] = mapped_column(DateTime)


class SupervisorGrupo(Base):
    """Equipes (grupo do Argus, `calls.grupo_origem`) que cada supervisor acompanha. Supervisor só vê as suas."""

    __tablename__ = "supervisor_grupos"
    __table_args__ = (UniqueConstraint("usuario_id", "grupo", name="uq_supervisor_grupo"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), index=True)
    grupo: Mapped[str] = mapped_column(String(128))


class AvaliacaoCiencia(Base):
    """O supervisor tomou ciência da avaliação e registrou a devolutiva dada ao operador (P3: o feedback
    chega ao operador pelo supervisor)."""

    __tablename__ = "avaliacao_ciencias"

    id: Mapped[int] = mapped_column(primary_key=True)
    avaliacao_id: Mapped[int] = mapped_column(ForeignKey("avaliacoes.id"), unique=True, index=True)
    usuario_id: Mapped[int | None] = mapped_column(Integer)
    usuario_nome: Mapped[str] = mapped_column(String(80))
    em: Mapped[datetime] = mapped_column(DateTime, default=agora)
    devolutiva: Mapped[str | None] = mapped_column(Text)


# --------------------------------------------------------------------------- controle de ponto (fase 4)
class PontoImportacao(Base):
    """Um CSV do Argus importado. tipo: ponto (entrada/saída) | pausas. Reimportar a mesma data substitui."""

    __tablename__ = "ponto_importacoes"

    id: Mapped[int] = mapped_column(primary_key=True)
    tipo: Mapped[str] = mapped_column(String(20), index=True)
    data_ref: Mapped[date] = mapped_column(Date, index=True)
    arquivo: Mapped[str | None] = mapped_column(String(200))
    linhas: Mapped[int] = mapped_column(Integer, default=0)
    importado_em: Mapped[datetime] = mapped_column(DateTime, default=agora)
    importado_por: Mapped[str | None] = mapped_column(String(80))


class PontoJornada(Base):
    """Linha do relatório de entrada/saída do Argus (um operador pode ter mais de uma no dia)."""

    __tablename__ = "ponto_jornadas"

    id: Mapped[int] = mapped_column(primary_key=True)
    importacao_id: Mapped[int] = mapped_column(ForeignKey("ponto_importacoes.id"), index=True)
    data: Mapped[date] = mapped_column(Date, index=True)
    grupo: Mapped[str | None] = mapped_column(String(128), index=True)
    operador: Mapped[str] = mapped_column(String(160), index=True)
    entrada_seg: Mapped[int | None] = mapped_column(Integer)  # segundos desde 00:00
    saida_seg: Mapped[int | None] = mapped_column(Integer)


class PontoPausa(Base):
    """Linha do relatório de pausas do Argus."""

    __tablename__ = "ponto_pausas"

    id: Mapped[int] = mapped_column(primary_key=True)
    importacao_id: Mapped[int] = mapped_column(ForeignKey("ponto_importacoes.id"), index=True)
    data: Mapped[date] = mapped_column(Date, index=True)  # dia do início da pausa
    grupo: Mapped[str | None] = mapped_column(String(128))
    operador: Mapped[str] = mapped_column(String(160), index=True)
    descricao: Mapped[str] = mapped_column(String(120))
    inicio: Mapped[datetime | None] = mapped_column(DateTime)
    fim: Mapped[datetime | None] = mapped_column(DateTime)
    segundos: Mapped[int] = mapped_column(Integer, default=0)


class PontoGrupo(Base):
    """Configuração por grupo do Argus (aba Config da planilha)."""

    __tablename__ = "ponto_grupos"

    grupo: Mapped[str] = mapped_column(String(128), primary_key=True)
    incluir: Mapped[bool] = mapped_column(Boolean, default=True)
    entrada_prevista: Mapped[str | None] = mapped_column(String(60))  # "10:00" ou "08:30;14:00" (vários turnos)
    tolerancia_min: Mapped[int] = mapped_column(Integer, default=10)


class PontoPausaConfig(Base):
    """Se a pausa conta no TMP/QTP (aba Config da planilha)."""

    __tablename__ = "ponto_pausas_config"

    descricao: Mapped[str] = mapped_column(String(120), primary_key=True)
    conta: Mapped[bool] = mapped_column(Boolean, default=True)


class Operador(Base):
    """Operador conhecido e a equipe atual dele (vem do "Grupo Atual" do relatório de ponto do Argus)."""

    __tablename__ = "operadores"

    chave: Mapped[str] = mapped_column(String(160), primary_key=True)  # nome normalizado
    nome: Mapped[str] = mapped_column(String(160))
    grupo: Mapped[str | None] = mapped_column(String(128))
    atualizado_em: Mapped[datetime | None] = mapped_column(DateTime)
    # vindos da API do Argus (/cmd/listarusuarios)
    ramal: Mapped[str | None] = mapped_column(String(40), index=True)  # = codUsuarioIntegracao do webhook
    id_usuario_argus: Mapped[int | None] = mapped_column(Integer)
    supervisor_argus: Mapped[str | None] = mapped_column(String(160))
    ativo: Mapped[bool | None] = mapped_column(Boolean)
    origem: Mapped[str | None] = mapped_column(String(20))  # argus | ponto
