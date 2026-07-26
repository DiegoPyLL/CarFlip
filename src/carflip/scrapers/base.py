import asyncio
import hashlib
import random
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from urllib.parse import urlparse, urlunparse

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from carflip.config import settings


def normalizar_url(url: str) -> str:
    """Quita query params, fragmento y trailing slash para hashing estable."""
    p = urlparse(url)
    return urlunparse(p._replace(query="", fragment="")).rstrip("/")


def construir_id_externo(url: str) -> str:
    """Identificador global estable y único: SHA256 del URL canónico."""
    return hashlib.sha256(normalizar_url(url).encode()).hexdigest()


# Sirven sobre valores explícitos ("Automática", "AT") y sobre títulos tipo
# ficha ("…DIESEL 4X2 AT8 5P"). No usar sobre descripciones largas: ahí
# "climatizador automático" daría falso positivo.
_PATRONES_TRANSMISION: list[tuple[re.Pattern, str]] = [
    (re.compile(r"autom[aá]tic|\bA/?T\d?\b|\bAUT\b|\bCVT\b|\bDSG\b|tiptronic|secuencial", re.IGNORECASE), "Automática"),
    (re.compile(r"mec[aá]nic|\bmanual\b|\bM/?T\d?\b|\bMEC\b", re.IGNORECASE), "Manual"),
]


def normalizar_transmision(texto: str | None) -> str | None:
    """Canoniza la transmisión a 'Manual' / 'Automática', los valores exactos
    que guarda el formulario de particulares (TRANSMISIONES en la web): así el
    filtro cruzado compara por igualdad, sin variantes ni tildes perdidas.

    Cubre el uso chileno real ("Mecánica" = manual) y las siglas de caja.
    Ante texto irreconocible devuelve None en vez de guardar basura.
    """
    if not texto:
        return None
    for patron, canonico in _PATRONES_TRANSMISION:
        if patron.search(texto):
            return canonico
    return None


def normalizar_traccion(valor: str | None) -> str | None:
    """Canoniza la tracción a '4x4' / 'Delantera' / 'Trasera' desde un valor
    explícito de la fuente (atributo del aviso o campo de API).

    "4x2" no se mapea: dice que un solo eje traicona pero no cuál.
    """
    if not valor:
        return None
    v = valor.strip().lower()
    if re.search(r"4\s?x\s?4|4wd|awd|integral|total", v):
        return "4x4"
    if "delanter" in v or "fwd" in v or "front" in v:
        return "Delantera"
    if "traser" in v or "rwd" in v or "propulsi" in v or "rear" in v:
        return "Trasera"
    return None


# Solo menciones inequívocas: una palabra suelta como "delantera" no cuenta
# ("cámara delantera" no es tracción). El orden importa: 4x4 primero, porque
# un aviso puede decir "4x4, tracción delantera desconectable".
_PATRONES_TRACCION: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b4\s?x\s?4\b|\b4wd\b|\bawd\b|tracci[oó]n\s+(?:integral|total)", re.IGNORECASE), "4x4"),
    (re.compile(r"tracci[oó]n\s+delantera", re.IGNORECASE), "Delantera"),
    (re.compile(r"tracci[oó]n\s+trasera|propulsi[oó]n\s+trasera", re.IGNORECASE), "Trasera"),
]


def traccion_desde_texto(*textos: str | None) -> str | None:
    """Respaldo cuando la fuente no publica la tracción como dato estructurado:
    la busca en título/descripción (ej. "…DIESEL 4X4 AT8…")."""
    for texto in textos:
        if not texto:
            continue
        for patron, canonico in _PATRONES_TRACCION:
            if patron.search(texto):
                return canonico
    return None


@dataclass
class AvisoAuto:
    """Datos normalizados de un aviso de auto."""

    fuente: str
    id_externo: str
    url: str
    titulo: str
    precio: Decimal | None = None
    moneda: str = "CLP"
    marca: str | None = None
    modelo: str | None = None
    anio: int | None = None
    km: int | None = None
    ubicacion: str | None = None
    combustible: str | None = None
    transmision: str | None = None
    traccion: str | None = None
    descripcion: str | None = None
    url_imagen: str | None = None
    disponible: bool | None = None
    fecha_publicacion: str | None = None

    @property
    def nombre_normalizado(self) -> str:
        def slug(s: str) -> str:
            return re.sub(r"[^\w]", "_", s.lower()).strip("_")

        url_hash = hashlib.sha256(self.url.encode()).hexdigest()[:8]
        partes = [self.fuente]
        if self.marca:
            partes.append(slug(self.marca))
        if self.modelo:
            partes.append(slug(self.modelo))
        if self.anio:
            partes.append(str(self.anio))
        partes.append(url_hash)
        return "_".join(partes)


@dataclass
class ResultadoScraping:
    fuente: str
    iniciado_en: datetime = field(default_factory=datetime.now)
    finalizado_en: datetime | None = None
    avisos: list[AvisoAuto] = field(default_factory=list)
    errores: int = 0


class ScraperBase(ABC):
    fuente: str = ""
    # Identificador único numérico por scraper, prefijo de id_externo.
    # 100=autocosmos, 101=yapo, 102=mercadolibre, 103=autosusados, 104=checkeados
    codigo_fuente: int = 0
    model_class: type | None = None  # tabla PostgreSQL destino, declarada en cada scraper
    # Métricas de la última corrida — lo llena scrape() y lo persiste ejecutar().
    ultimo_reporte: dict | None = None

    async def ejecutar(self, sesion: AsyncSession) -> ResultadoScraping:
        from carflip.database.uploader import upsert_avisos
        from carflip.scrapers.logging_utils import log_banner_fase

        resultado = ResultadoScraping(fuente=self.fuente)
        log_banner_fase(self.fuente, 0, "INICIO")
        logger.info(f"[{self.fuente}] Iniciando scraping")
        try:
            avisos = await self.scrape()
            resultado.avisos = avisos

            if avisos and self.model_class is not None:
                log_banner_fase(self.fuente, 4, "CARGA BD")
                n = await upsert_avisos(sesion, avisos, self.model_class)
                logger.info(
                    f"[{self.fuente}] CARGA BD — {n} avisos upserted en {self.model_class.__tablename__}"
                )
            else:
                logger.info(f"[{self.fuente}] {len(avisos)} avisos obtenidos (sin carga a BD)")
        except Exception as exc:
            resultado.errores += 1
            logger.error(f"[{self.fuente}] Error fatal: {exc}")

        # Un fallo guardando métricas no debe invalidar los avisos ya cargados.
        if self.ultimo_reporte is not None:
            from carflip.database.metricas import guardar_run_report

            try:
                await guardar_run_report(sesion, self.ultimo_reporte)
            except Exception:
                logger.exception(f"[{self.fuente}] No se pudieron guardar las métricas de la corrida")

        resultado.finalizado_en = datetime.now()
        return resultado

    @abstractmethod
    async def scrape(self) -> list[AvisoAuto]:
        """Implementar la lógica de scraping de cada sitio."""

    async def espera_aleatoria(self) -> None:
        espera = random.uniform(settings.min_delay_seconds, settings.max_delay_seconds)
        await asyncio.sleep(espera)
