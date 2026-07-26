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

    # Yapo — tuning ajustable por entorno (CI vs. local). Los valores por
    # defecto están calibrados para GitHub Actions (2 vCPU, sin créditos de CPU).
    yapo_concurrencia_detalles: int = 2      # páginas de detalle en paralelo
    yapo_max_avisos: int = 1_000             # tope de publicaciones por corrida
    yapo_pausa_lote_seg: float = 0.0         # pausa entre lotes (0 = sin pausa)
    yapo_reciclar_cada: int = 50             # recrear el navegador cada N detalles
    yapo_presupuesto_min: float = 180.0      # tope de minutos de ingesta antes de cerrar ordenado

    # Reintentos de subida a R2. Backoff exponencial: base * 2**(intento-1).
    # Corto por diseño: una foto no debe poder colgar un run de CI.
    r2_max_reintentos: int = 4
    r2_backoff_base_seg: float = 5.0

    # Detección de deals
    deal_threshold_pct: float = 15.0        # % bajo la mediana del grupo para ser candidato
    deal_min_comparables: int = 5           # mínimo de avisos por grupo marca/modelo/año
    deal_min_comparables_particular: int = 12  # más exigente: el aviso de un particular no lo filtró ningún portal
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

    # Cloudflare R2 — almacenamiento de las fotos
    r2_account_id: str = ""
    r2_bucket: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""

    # Dominio público desde el que se sirven las fotos de R2
    cdn_base_url: str = ""


settings = Settings()
