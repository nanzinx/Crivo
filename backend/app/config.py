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

    # ----- Detecção local de fala (sem IA) -----
    vad_ativo: bool = True
    vad_fala_minima_segundos: float = 0.6  # menos fala que isso = "Mudo total" sem chamar a IA
    suspeita_fala_canal_segundos: float = 3  # estéreo: fala em CADA lado para suspeitar de conversa
    suspeita_fala_mono_segundos: float = 20  # mono: fala total para suspeitar de conversa

    # Divergência só é apontada com confiança da IA a partir daqui; abaixo, vai para revisão humana
    confianca_minima_divergencia: float = 0.6

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
