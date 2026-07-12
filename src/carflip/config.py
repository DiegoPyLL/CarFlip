from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_ROOT = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "postgresql+asyncpg://user:password@localhost:5432/carflip"

    mercadolibre_app_id: str = ""
    mercadolibre_client_secret: str = ""

    scrape_interval_hours: int = 24 #una vez al día
    delay_entre_scrapers_segundos: int = 30
    min_delay_seconds: float = 2.0
    max_delay_seconds: float = 6.0

    # Detección de deals
    deal_threshold_pct: float = 15.0        # % bajo la mediana del grupo para ser candidato
    deal_min_comparables: int = 5           # mínimo de avisos por grupo marca/modelo/año
    deal_max_candidatos: int = 200          # tope de candidatos por corrida
    deal_lote_ia: int = 10                  # candidatos por request a Groq
    deal_recategorizar_dias: int = 7        # re-categorizar aunque no cambie el precio tras N días

    # Groq (categorización IA de deals)
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"

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
