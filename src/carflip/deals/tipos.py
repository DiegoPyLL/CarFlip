"""Dataclasses compartidos del pipeline de deals."""

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass
class CandidatoDeal:
    """Fila retornada por candidatos.sql: aviso + contexto de mercado."""

    fuente: str
    id_externo: str
    url: str
    titulo: str
    precio: Decimal
    moneda: str = "CLP"
    marca: str | None = None
    modelo: str | None = None
    anio: int | None = None
    km: int | None = None
    ubicacion: str | None = None
    transmision: str | None = None
    traccion: str | None = None
    descripcion: str | None = None
    url_imagen: str | None = None
    delta_pct: float | None = None
    precio_mercado: Decimal | None = None
    comparables: int | None = None
    pct_vs_mercado: float | None = None

    @property
    def id_ia(self) -> str:
        """ID único enviado al LLM para desambiguar fuentes dentro de un lote."""
        return f"{self.fuente}-{self.id_externo}"


@dataclass
class EvaluacionDeal:
    """Veredicto del LLM para un candidato."""

    fuente: str
    id_externo: str
    categoria: str  # oportunidad_clara | buen_precio | revisar | descartar
    puntaje: int  # 0-100
    riesgos: list[str] = field(default_factory=list)
    resumen: str = ""
