from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]  # raiz do repositório
DATA = ROOT / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(str(ROOT / ".env"), str(ROOT / "backend" / ".env")), extra="ignore"
    )

    argus_base_url: str = "https://argus.app.br/apiargus"
    argus_token: str = ""
    argus_campaign_ids: str = ""  # ex.: "12,15" (usado no polling/backfill)
    argus_audio_format: str = "MP3"
    argus_audio_channels: int = 1  # 1 mono | 2 estéreo | 3 estéreo separando pontas A/B
    argus_canal_operador: int = 0  # no estéreo separado: 0 = operador no canal esquerdo (ponta A), 1 = direito
    argus_webhook_secret: str = ""
    argus_poll_minutos: int = 5  # intervalo do polling de fallback

    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    # Transcrição: gpt-4o-mini-transcribe custa cerca de metade do whisper-1 (valide com scripts/comparar_transcricao)
    openai_whisper_model: str = "gpt-4o-mini-transcribe"

    # ----- Custo de IA -----
    ia_diarizar: bool = False  # True = a IA reescreve a conversa separada por falante (resposta ~5x maior)
    ia_teto_diario_usd: float = 0  # 0 = sem teto; ao atingir, as ligações ficam "aguardando IA" até o dia seguinte
    # Preços (US$). 0 = usar a tabela de app/services/custos.py para o modelo configurado
    preco_transcricao_minuto: float = 0
    preco_entrada_1m: float = 0
    preco_saida_1m: float = 0

    # ----- Tratamento do áudio antes de transcrever (sem IA) -----
    cortar_silencio: bool = True  # remove espera/silêncio longos: a transcrição é cobrada por duração
    transcricao_por_canal: bool = True  # estéreo separado: transcreve operador e cliente em separado

    # ----- Detecção local de fala (sem IA) -----
    vad_ativo: bool = True
    vad_fala_minima_segundos: float = 0.6  # menos fala que isso = "Mudo total" sem chamar a IA
    suspeita_fala_canal_segundos: float = 3  # estéreo: fala em CADA lado para suspeitar de conversa
    suspeita_fala_mono_segundos: float = 20  # mono: fala total para suspeitar de conversa

    # Divergência só é apontada com confiança da IA a partir daqui; abaixo, vai para revisão humana
    confianca_minima_divergencia: float = 0.6

    # Porcentagem das ligações analisadas que vai, por sorteio, para a fila de revisão humana.
    # Mede a IA sem viés: se só os casos duvidosos fossem revisados, a acurácia pareceria pior do que é.
    amostra_qualidade_pct: float = 2

    # ----- Alertas automáticos (avaliados a cada ALERTA_INTERVALO_MINUTOS) -----
    alerta_intervalo_minutos: int = 15
    alerta_operador_horas: int = 24  # janela analisada por operador
    alerta_operador_min_ligacoes: int = 20  # menos que isso: amostra pequena demais para acusar
    alerta_operador_taxa: float = 20  # % de divergência que gera alerta (atenção)
    alerta_operador_altas: int = 5  # divergências de gravidade alta que tornam o alerta crítico
    alerta_tronco_horas: int = 3
    alerta_tronco_min_ligacoes: int = 20
    alerta_tronco_mudas_pct: float = 40  # % de ligações mudas no tronco (atenção; crítico a partir de 70%)
    alerta_renotificar_horas: int = 6  # não repete a notificação do mesmo alerta antes disso

    # ----- Relatório diário -----
    relatorio_hora: int = 19  # gera e envia o relatório do dia a partir desta hora
    relatorio_dias: str = "0-5"  # dias da semana (0 = segunda ... 6 = domingo)

    # ----- Notificações (alertas e relatório). Sem configuração: só aparecem no painel -----
    notificar_webhook_url: str = ""  # Slack, Microsoft Teams ou Google Chat (webhook de entrada)
    smtp_host: str = ""
    smtp_porta: int = 587
    smtp_usuario: str = ""
    smtp_senha: str = ""
    smtp_tls: bool = True
    smtp_remetente: str = ""
    notificar_emails: str = ""  # destinatários, separados por vírgula
    painel_url: str = ""  # endereço do painel, para os links nas mensagens (ex.: http://crivo.empresa:3000)

    # ----- Acesso -----
    auth_ativo: bool = True  # false só para desenvolvimento local: sem login, todos entram como administrador
    sessao_horas: int = 12
    cookie_seguro: bool = False  # true quando o painel estiver atrás de HTTPS

    database_url: str = f"sqlite:///{(DATA / 'crivo.db').as_posix()}"
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    recordings_dir: str = str(DATA / "gravacoes")
    legacy_csv: str = str(DATA / "relatorio_escuta_gravacoes.csv")
    legacy_html: str = str(DATA / "dashboard_gravacoes.html")
    cruzar_csv: str = str(DATA / "cruzar_dados.csv")
    argus_download_dir: str = str(DATA / "argus")

    # Painel de saúde
    alerta_webhook_minutos: int = 30  # sem webhook há mais que isso, em horário comercial => alerta
    horario_comercial: str = "8-20"  # horas (inclusivo-exclusivo) de seg a sáb
    alerta_fila_max: int = 200

    def model_post_init(self, __context) -> None:
        # Caminhos relativos do .env valem a partir da raiz do repositório (não do diretório atual)
        for campo in ("recordings_dir", "legacy_csv", "legacy_html", "cruzar_csv", "argus_download_dir"):
            p = Path(getattr(self, campo))
            if not p.is_absolute():
                object.__setattr__(self, campo, str((ROOT / p).resolve()))

    @property
    def resolved_database_url(self) -> str:
        url = self.database_url
        if url.startswith("sqlite:///"):
            p = Path(url[len("sqlite:///"):])
            if not p.is_absolute():
                p = (ROOT / p).resolve()
            p.parent.mkdir(parents=True, exist_ok=True)
            return f"sqlite:///{p.as_posix()}"
        return url

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
