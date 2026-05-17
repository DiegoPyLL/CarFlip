from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+asyncpg://user:password@localhost:5432/carflip"

    mercadolibre_app_id: str = ""
    mercadolibre_client_secret: str = ""

    scrape_interval_hours: int = 6
    min_delay_seconds: float = 2.0
    max_delay_seconds: float = 6.0
    deal_threshold_pct: float = 15.0

    log_level: str = "INFO"
    log_file: str = "logs/carflip.log"

    use_ssl: bool = False

    output_dir: str = "data/raw"


settings = Settings()
