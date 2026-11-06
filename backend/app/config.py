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
    openai_whisper_model: str = "whisper-1"

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
