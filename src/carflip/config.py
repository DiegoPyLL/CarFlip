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

    # Detección de deals
    deal_threshold_pct: float = 15.0        # % bajo la mediana del grupo para ser candidato
    # Exigente a propósito: ningún aviso pasó por el filtro de un portal, así que
    # un grupo comparable chico dejaría entrar precios irreales como oportunidad.
    deal_min_comparables: int = 12          # mínimo de avisos por grupo marca/modelo/año
    deal_max_candidatos: int = 200          # tope de candidatos por corrida
    deal_lote_ia: int = 10                  # candidatos por request a Groq
    deal_recategorizar_dias: int = 7        # re-categorizar aunque no cambie el precio tras N días

    # Groq (categorización IA de deals)
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"

    log_level: str = "INFO"
    log_file: str = "logs/carflip.log"

    use_ssl: bool = False


settings = Settings()
