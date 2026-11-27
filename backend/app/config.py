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
    argus_webhook_secret: str = ""
    argus_poll_minutos: int = 5  # intervalo do polling de fallback

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
    alerta_nota_dias: int = 7  # janela da nota do script por operador
    alerta_nota_minima: float = 70  # nota média abaixo disso gera alerta (crítico abaixo de 50)
    alerta_nota_min_avaliacoes: int = 3  # menos avaliações que isso: amostra pequena demais
    alerta_atraso_dias: int = 7  # dias de ponto olhados para atraso recorrente
    alerta_atrasos_min: int = 3  # atrasos nessa janela que geram alerta

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
    argus_ponto_automatico: bool = True  # com ARGUS_TOKEN: busca o ponto (entrada/saída e pausas) pela API
    argus_ponto_minutos: int = 30  # de quanto em quanto tempo atualiza o ponto de hoje e os operadores
    zip_max_gravacoes: int = 1000  # limite de gravações por arquivo .zip exportado
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
