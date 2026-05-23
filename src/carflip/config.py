from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+asyncpg://user:password@localhost:5432/carflip"

    mercadolibre_app_id: str = ""
    mercadolibre_client_secret: str = ""

    scrape_interval_hours: int = 12
    delay_entre_scrapers_segundos: int = 30
    min_delay_seconds: float = 2.0
    max_delay_seconds: float = 6.0
    deal_threshold_pct: float = 15.0

    log_level: str = "INFO"
    log_file: str = "logs/carflip.log"

    use_ssl: bool = False

    output_dir: str = "data/raw"
    processed_dir: str = "data/processed"

    r2_account_id: str = ""
    r2_bucket: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_prefix: str = "autocosmos/fotos/"

    s3_bucket: str = ""
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    s3_region: str = "us-east-1"
    s3_prefix: str = "autocosmos/"

    # CloudFront (sin dominio propio: https://dxxxx.cloudfront.net)
    cdn_base_url: str = ""


settings = Settings()
