from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(str(ROOT.parent / ".env"), str(ROOT / ".env")), extra="ignore"
    )

    argus_base_url: str = "https://argus.app.br/apiargus"
    argus_token: str = ""
    argus_campaign_ids: str = ""  # ex.: "12,15" (usado no polling/backfill)
    argus_audio_format: str = "MP3"
    argus_audio_channels: int = 1  # 1 mono | 2 estéreo | 3 estéreo separando pontas A/B
    argus_webhook_secret: str = ""

    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_whisper_model: str = "whisper-1"

    database_url: str = f"sqlite:///{(ROOT / 'supervisor.db').as_posix()}"

    recordings_dir: str = "c:/Projetos/testes/Gravações"
    legacy_csv: str = "c:/Projetos/testes/relatorio_escuta_gravacoes.csv"
    legacy_html: str = "c:/Projetos/testes/dashboard_gravacoes.html"
    cruzar_csv: str = "c:/Projetos/testes/cruzar_dados.csv"
    argus_download_dir: str = str(ROOT / "data" / "argus")

    @property
    def resolved_database_url(self) -> str:
        url = self.database_url
        if url.startswith("sqlite:///"):
            path_part = url[len("sqlite:///"):]
            p = Path(path_part)
            if not p.is_absolute():
                abs_path = (ROOT / p).resolve().as_posix()
                return f"sqlite:///{abs_path}"
        return url


settings = Settings()
