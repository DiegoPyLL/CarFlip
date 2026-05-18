"""
Pipeline cloud completo para Autocosmos Chile.

Etapas cubiertas en scrape():
  1. INGESTA      — paginación HTTP, parseo de cards, descarga de fotos, guardado JSON por página
  2. LIMPIEZA     — deduplicación por id_externo (fotos y JSON)
  3. VALIDACIÓN   — validación estructural y semántica; avisos inválidos van a FAIL LOG
  4. CARGA        — delegada a ScraperBase.ejecutar() vía uploader.upsert_avisos()
"""


#TODO (Definir formato de archivo para el log )



import asyncio
import hashlib
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urljoin

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parents[4]))

import aioboto3
import httpx
from botocore.exceptions import ClientError
from bs4 import BeautifulSoup, Tag
from fake_useragent import UserAgent
from loguru import logger

from sqlalchemy.ext.asyncio import AsyncSession

from carflip.config import settings
from carflip.database.models import AutocosmosListing
from carflip.database.uploader import guardar_resultado_scraping
from carflip.scrapers.base import AvisoAuto, ResultadoScraping, ScraperBase

BASE_URL = "https://www.autocosmos.cl"
URL_USADOS = f"{BASE_URL}/auto/usado"

_PATRON_AVISO = re.compile(r"^/auto/usado/[^/]+/[^/]+/[^/]+/(\d+)")
_PATRON_FECHA = re.compile(r"^\d{4}-\d{2}-\d{2}$")

_AÑO_MINIMO = 1970
_PRECIO_MINIMO = 500_000
_PRECIO_MAXIMO = 250_000_000

_S3_MAX_REINTENTOS = 12   # 12 × 10 min = 2 horas
_S3_INTERVALO_SEG  = 600  # 10 minutos
_MAX_REINTENTOS_GET = 10  # reintentos por página antes de saltar a la siguiente


# ─── CARGA S3 ────────────────────────────────────────────────────────────────


async def _cargar_a_s3_con_retry(ruta_local: Path, clave_s3: str) -> bool:
    """
    Sube `ruta_local` a S3 bajo la clave `clave_s3`.
    Verifica que el objeto exista tras la subida.
    Reintenta cada 10 min por un máximo de 2 horas (12 intentos).
    Retorna True si la carga fue exitosa, False si se agotaron los reintentos.
    """
    sesion = aioboto3.Session(
        aws_access_key_id=settings.s3_access_key_id,
        aws_secret_access_key=settings.s3_secret_access_key,
        region_name=settings.s3_region,
    )
    datos = ruta_local.read_bytes()

    async with sesion.client("s3") as cliente:  # type: ignore[attr-defined]  # aioboto3 no tiene stubs completos
        for intento in range(1, _S3_MAX_REINTENTOS + 1):
            try:
                await cliente.put_object(Bucket=settings.s3_bucket, Key=clave_s3, Body=datos)
                await cliente.head_object(Bucket=settings.s3_bucket, Key=clave_s3)
                logger.debug(f"[autocosmos] S3 upload OK: {clave_s3}")
                return True

            except (ClientError, Exception) as exc:
                if intento < _S3_MAX_REINTENTOS:
                    logger.warning(
                        f"[autocosmos] S3 upload fallido intento {intento}/{_S3_MAX_REINTENTOS}"
                        f" — {clave_s3}: {exc}. Reintentando en {_S3_INTERVALO_SEG // 60} min."
                    )
                    await asyncio.sleep(_S3_INTERVALO_SEG)
                else:
                    logger.error(
                        f"[autocosmos] S3 upload agotó {_S3_MAX_REINTENTOS} reintentos: {clave_s3} — {exc}"
                    )

    return False


# ─── FAIL LOG ────────────────────────────────────────────────────────────────


@dataclass
class FailLog:
    etapa: str
    motivo: str
    id_externo: str
    fuente: str = "autocosmos"
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ─── VALIDACIÓN ──────────────────────────────────────────────────────────────


def _validar_aviso(aviso: AvisoAuto) -> list[str]:
    """Retorna lista de errores. Lista vacía = aviso válido."""
    errores: list[str] = []
    anio_actual = datetime.now().year

    # Estructurales
    if aviso.anio is not None:
        s = str(aviso.anio)
        if not (s.isdigit() and len(s) == 4):
            errores.append(f"anio con formato inválido: {aviso.anio!r}")

    if aviso.precio is not None and aviso.precio <= 0:
        errores.append(f"precio debe ser > 0, es {aviso.precio}")

    if aviso.km is not None and aviso.km < 0:
        errores.append(f"km debe ser >= 0, es {aviso.km}")

    if aviso.fecha_publicacion is not None:
        if not _PATRON_FECHA.match(aviso.fecha_publicacion):
            errores.append(f"fecha_publicacion no es YYYY-MM-DD: {aviso.fecha_publicacion!r}")
        else:
            try:
                fecha = datetime.strptime(aviso.fecha_publicacion, "%Y-%m-%d").date()
                if fecha > datetime.now().date():
                    errores.append(f"fecha_publicacion es futura: {aviso.fecha_publicacion}")
            except ValueError:
                errores.append(f"fecha_publicacion inválida: {aviso.fecha_publicacion!r}")

    # Semánticas (solo si no hay error estructural en anio)
    if aviso.anio is not None and not any("anio" in e for e in errores):
        if not (_AÑO_MINIMO <= aviso.anio <= anio_actual):
            errores.append(f"anio {aviso.anio} fuera de rango [{_AÑO_MINIMO}, {anio_actual}]")

    if aviso.precio is not None:
        if not (_PRECIO_MINIMO <= float(aviso.precio) <= _PRECIO_MAXIMO):
            errores.append(
                f"precio {aviso.precio} fuera de rango [{_PRECIO_MINIMO:,}, {_PRECIO_MAXIMO:,}] CLP"
            )

    return errores


# ─── HELPERS DE ALMACENAMIENTO RAW ───────────────────────────────────────────


def _carpeta_run(base: Path, fecha_str: str) -> Path:
    carpeta = base / f"autocosmos_{fecha_str}"
    (carpeta / "fotos").mkdir(parents=True, exist_ok=True)
    return carpeta


def _aviso_a_dict(aviso: AvisoAuto, foto_local: str | None = None) -> dict:
    return {
        "fuente": aviso.fuente,
        "id_externo": aviso.id_externo,
        "url": aviso.url,
        "titulo": aviso.titulo,
        "precio": str(aviso.precio) if aviso.precio is not None else None,
        "moneda": aviso.moneda,
        "marca": aviso.marca,
        "modelo": aviso.modelo,
        "anio": aviso.anio,
        "km": aviso.km,
        "ubicacion": aviso.ubicacion,
        "combustible": aviso.combustible,
        "descripcion": aviso.descripcion,
        "url_imagen": aviso.url_imagen,
        "foto_local": foto_local,
        "disponible": aviso.disponible,
        "fecha_publicacion": aviso.fecha_publicacion,
    }


def _append_avisos_jsonl(
    avisos: list[AvisoAuto],
    ruta_jsonl: Path,
    fotos: dict[str, str] | None = None,
) -> bool:
    """Append avisos a un JSONL, una línea por aviso."""
    if fotos is None:
        fotos = {}
    try:
        with open(ruta_jsonl, "a", encoding="utf-8") as f:
            for aviso in avisos:
                linea = json.dumps(
                    _aviso_a_dict(aviso, foto_local=fotos.get(aviso.id_externo)),
                    ensure_ascii=False,
                )
                f.write(linea + "\n")
        logger.debug(f"[autocosmos] {len(avisos)} avisos appended a {ruta_jsonl.name}")
        return True
    except Exception as e:
        logger.error(f"[autocosmos] Error appending avisos a JSONL: {e}")
        return False


async def _descargar_imagen(
    cliente: httpx.AsyncClient,
    aviso: AvisoAuto,
    carpeta_fotos: Path,
    ua: UserAgent,
) -> Path | None:
    if not aviso.url_imagen:
        return None
    ext = Path(aviso.url_imagen.split("?")[0]).suffix or ".jpg"
    ruta = carpeta_fotos / f"{aviso.id_externo}{ext}"
    if ruta.exists():
        logger.debug(f"[autocosmos] Imagen ya existe: {ruta.name}")
        return ruta
    try:
        resp = await cliente.get(aviso.url_imagen, headers={"User-Agent": ua.random}, timeout=20.0)
        resp.raise_for_status()
        ruta.write_bytes(resp.content)
        logger.debug(f"[autocosmos] Imagen descargada: id={aviso.id_externo} → {ruta.name}")
        return ruta
    except Exception as e:
        logger.warning(f"[autocosmos] No se pudo descargar imagen id={aviso.id_externo}: {e}")
        return None


# ─── PARSEO HTML ─────────────────────────────────────────────────────────────


def _parsear_precio(texto: str) -> Decimal | None:
    match = re.search(r"\$\s*([\d.,]+)", texto)
    if not match:
        return None
    try:
        return Decimal(match.group(1).replace(".", "").replace(",", ""))
    except InvalidOperation:
        return None


def _parsear_km(texto: str) -> int | None:
    match = re.search(r"([\d.,]+)\s*km", texto, re.IGNORECASE)
    if not match:
        return None
    try:
        return int(match.group(1).replace(".", "").replace(",", ""))
    except ValueError:
        return None


def _parsear_anio(texto: str) -> int | None:
    match = re.search(r"\b(19|20)\d{2}\b", texto)
    if not match:
        return None
    try:
        return int(match.group(0))
    except ValueError:
        return None


def _parsear_ubicacion(texto: str) -> str | None:
    for parte in (p.strip() for p in texto.split("|")):
        if parte and not re.search(r"[\d$]", parte):
            return parte
    return None


def _parsear_aviso(tag: Tag) -> AvisoAuto | None:
    href = str(tag.get("href", ""))
    match = _PATRON_AVISO.match(href)
    if not match:
        return None

    url = urljoin(BASE_URL, href)
    id_externo = hashlib.sha256(url.encode()).hexdigest()

    partes = href.rstrip("/").split("/")
    marca = partes[3].replace("-", " ").title() if len(partes) > 3 else None
    modelo = partes[4].replace("-", " ").title() if len(partes) > 4 else None

    img = tag.find("img")
    url_imagen: str | None = None
    titulo: str | None = None
    if isinstance(img, Tag):
        url_imagen = img.get("src") or img.get("data-src")
        titulo = img.get("alt")

    texto = tag.get_text(separator=" ", strip=True)
    if not titulo:
        titulo = texto[:200]

    precio = _parsear_precio(texto)
    km = _parsear_km(texto)

    # Advertencias de ingesta por campos recuperables faltantes
    if not titulo:
        logger.warning(f"[autocosmos] id={id_externo} sin título, usando fallback")
    if precio is None:
        logger.warning(f"[autocosmos] id={id_externo} sin precio")
    if km is None:
        logger.warning(f"[autocosmos] id={id_externo} km no encontrado")

    return AvisoAuto(
        fuente="autocosmos",
        id_externo=id_externo,
        url=url,
        titulo=titulo or "",
        precio=precio,
        moneda="CLP",
        marca=marca,
        modelo=modelo,
        anio=_parsear_anio(texto),
        km=km,
        ubicacion=_parsear_ubicacion(texto),
        url_imagen=url_imagen,
        disponible=True,
    )


def _extraer_cards(html: str, vistos: set[str]) -> list[Tag]:
    soup = BeautifulSoup(html, "lxml")
    cards: list[Tag] = []
    for a in soup.find_all("a", href=True):
        href = str(a.get("href", ""))
        if _PATRON_AVISO.match(href) and href not in vistos:
            vistos.add(href)
            cards.append(a)
    return cards


# ─── SCRAPER CLOUD ────────────────────────────────────────────────────────────


class ScraperAutocosmosCloud(ScraperBase):
    """
    Scraper de Autocosmos con pipeline cloud completo:
    ingesta → limpieza → validación → retorno para carga.
    """

    fuente = "autocosmos"
    model_class = AutocosmosListing

    def __init__(self, max_paginas: int | None = None, guardar_raw: bool = True) -> None:
        self.max_paginas = max_paginas
        self.guardar_raw = guardar_raw
        self._ua = UserAgent()

    async def ejecutar(self, sesion: AsyncSession) -> ResultadoScraping:
        resultado = await super().ejecutar(sesion)
        await guardar_resultado_scraping(sesion, resultado)
        return resultado

    async def scrape(self) -> list[AvisoAuto]:
        utc_4 = timezone(timedelta(hours=-4))
        inicio = datetime.now(utc_4)
        logger.info(f"[autocosmos] Iniciando scrape cloud — {inicio.strftime('%H:%M:%S %d/%m/%Y')}")

        fail_logs: list[FailLog] = []
        avisos_raw: list[AvisoAuto] = []
        vistos_href: set[str] = set()
        paginas_procesadas = 0

        fecha_str = inicio.strftime("%H-%M-%S_%d-%m-%Y")
        carpeta = _carpeta_run(Path(settings.output_dir), fecha_str) if self.guardar_raw else None
        ruta_jsonl = carpeta / "avisos.jsonl" if carpeta else None



        # ── INGESTA ──────────────────────────────────────────────────────────
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as cliente:
            pagina = 1
            while self.max_paginas is None or pagina <= self.max_paginas:
                response = None
                for intento in range(1, _MAX_REINTENTOS_GET + 1):
                    logger.debug(
                        f"[autocosmos] GET {URL_USADOS} params={{pidx: {pagina}}}"
                        + (f" — intento {intento}/{_MAX_REINTENTOS_GET}" if intento > 1 else "")
                    )
                    try:
                        headers = {"User-Agent": self._ua.random}
                        response = await cliente.get(
                            URL_USADOS, params={"pidx": pagina}, headers=headers
                        )
                        response.raise_for_status()
                        logger.debug(f"[autocosmos] HTTP {response.status_code} — {response.url}")
                        break
                    except Exception as e:
                        if intento < _MAX_REINTENTOS_GET:
                            logger.warning(
                                f"[autocosmos] Error en página {pagina}"
                                f" intento {intento}/{_MAX_REINTENTOS_GET}: {e} — reintentando en 2s"
                            )
                            await asyncio.sleep(2)
                        else:
                            logger.error(
                                f"[autocosmos] Página {pagina}: agotados {_MAX_REINTENTOS_GET}"
                                f" reintentos, continuando con siguiente página"
                            )
                if response is None:
                    pagina += 1
                    continue

                cards = _extraer_cards(response.text, vistos_href)
                if not cards:
                    logger.info(f"[autocosmos] Página {pagina}: sin resultados, fin paginación")
                    break

                avisos_pagina: list[AvisoAuto] = []
                for card in cards:
                    try:
                        aviso = _parsear_aviso(card)
                        if aviso:
                            logger.debug(f"[autocosmos] Parseando aviso id={aviso.id_externo}")
                            avisos_pagina.append(aviso)
                    except Exception as e:
                        logger.warning(f"[autocosmos] Error parseando card en página {pagina}: {e}")

                # Batch: descargar fotos antes de avanzar página
                fotos_pagina: dict[str, str] = {}
                if self.guardar_raw and carpeta and avisos_pagina:
                    carpeta_fotos = carpeta / "fotos"
                    tareas_img = [
                        _descargar_imagen(cliente, a, carpeta_fotos, self._ua)
                        for a in avisos_pagina
                        if a.url_imagen
                    ]
                    if tareas_img:
                        resultados = await asyncio.gather(*tareas_img, return_exceptions=True)
                        avisos_con_imagen = [a for a in avisos_pagina if a.url_imagen]
                        tareas_s3: list = []
                        for aviso, resultado in zip(avisos_con_imagen, resultados):
                            if isinstance(resultado, Path):
                                fotos_pagina[aviso.id_externo] = resultado.name
                                clave = f"{settings.s3_prefix}fotos/autocosmos-{fecha_str}-{resultado.name}"
                                tareas_s3.append(_cargar_a_s3_con_retry(resultado, clave))
                            elif resultado is None or isinstance(resultado, Exception):
                                fail_logs.append(FailLog(
                                    etapa="descarga_foto",
                                    motivo="Descarga de imagen fallida",
                                    id_externo=aviso.id_externo,
                                ))
                        imgs_ok = sum(1 for r in resultados if isinstance(r, Path))
                        imgs_fail = len(resultados) - imgs_ok
                        logger.info(
                            f"[autocosmos] Página {pagina}: {imgs_ok}/{len(resultados)} Publicación scrapeada"
                            + (f" ({imgs_fail} fallida)" if imgs_fail else "")
                        )
                        if tareas_s3:
                            await asyncio.gather(*tareas_s3)

                # Append JSONL
                if self.guardar_raw and ruta_jsonl and avisos_pagina:
                    ok = _append_avisos_jsonl(avisos_pagina, ruta_jsonl, fotos=fotos_pagina)
                    if not ok:
                        for aviso in avisos_pagina:
                            fail_logs.append(FailLog(
                                etapa="dedup_json",
                                motivo=f"Error al serializar JSONL página {pagina}",
                                id_externo=aviso.id_externo,
                            ))

                avisos_raw.extend(avisos_pagina)
                logger.debug(f"[autocosmos] Página {pagina}: {len(avisos_pagina)} avisos obtenidos")
                paginas_procesadas += 1
                pagina += 1
                await self.espera_aleatoria()

        logger.info(
            f"[autocosmos] Ingesta completa — {len(avisos_raw)} avisos en {paginas_procesadas} páginas"
        )




        # ── LIMPIEZA (deduplicación por id_externo) ───────────────────────────
        vistos_id: set[str] = set()
        avisos_unicos: list[AvisoAuto] = []
        for aviso in avisos_raw:
            if aviso.id_externo in vistos_id:
                logger.warning(f"[autocosmos] Duplicado detectado id={aviso.id_externo}, descartando")
                fail_logs.append(FailLog(
                    etapa="dedup_json",
                    motivo="id_externo duplicado entre páginas",
                    id_externo=aviso.id_externo,
                ))
            else:
                vistos_id.add(aviso.id_externo)
                avisos_unicos.append(aviso)

        dups = len(avisos_raw) - len(avisos_unicos)
        logger.info(
            f"[autocosmos] Deduplicación: {len(avisos_raw)} → {len(avisos_unicos)} únicos"
            f" ({dups} descartados)"
        )


# TODO:( hacer que la validación y limpieza ocurra despues del guardado en data/raw )


        # ── VALIDACIÓN ────────────────────────────────────────────────────────
        avisos_validos: list[AvisoAuto] = []
        rechazados = 0
        for aviso in avisos_unicos:
            errores = _validar_aviso(aviso)
            if errores:
                logger.error(f"[autocosmos] Aviso rechazado id={aviso.id_externo}: {errores}")
                fail_logs.append(FailLog(
                    etapa="validacion_json",
                    motivo="; ".join(errores),
                    id_externo=aviso.id_externo,
                ))
                rechazados += 1
            else:
                avisos_validos.append(aviso)

        logger.info(
            f"[autocosmos] Validación: {len(avisos_validos)}/{len(avisos_unicos)} avisos pasan"
            f" ({rechazados} rechazados)"
        )









        # ── PROCESADOS (limpieza + validación superada) ──────────────────────
        if self.guardar_raw and avisos_validos:
            carpeta_procesados = Path(settings.processed_dir) / f"autocosmos_{fecha_str}"
            carpeta_procesados.mkdir(parents=True, exist_ok=True)
            ruta_procesados = carpeta_procesados / "avisos.jsonl"
            ok = _append_avisos_jsonl(avisos_validos, ruta_procesados)
            if ok:
                logger.info(
                    f"[autocosmos] {len(avisos_validos)} avisos procesados escritos en {ruta_procesados}"
                )
            else:
                logger.error(f"[autocosmos] Error al escribir avisos procesados en {ruta_procesados}")

        # ── FAIL LOGs consolidados ────────────────────────────────────────────
        if fail_logs:
            if self.guardar_raw and carpeta:
                ruta_fail = carpeta / "fail_logs.json"
                try:
                    ruta_fail.write_text(
                        json.dumps([asdict(fl) for fl in fail_logs], ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                    logger.info(f"[autocosmos] {len(fail_logs)} FAIL LOGs escritos en {ruta_fail}")
                    await _cargar_a_s3_con_retry(
                        ruta_fail,
                        f"{settings.s3_prefix}logs/autocosmos-{fecha_str}-{ruta_fail.name}",
                    )
                except Exception as e:
                    logger.error(f"[autocosmos] No se pudo escribir fail_logs.json: {e}")
            else:
                logger.info(
                    f"[autocosmos] {len(fail_logs)} FAIL LOGs generados (guardar_raw=False, no persistidos)"
                )

        # ── Metadata JSONL ────────────────────────────────────────────────────
        if self.guardar_raw and ruta_jsonl and ruta_jsonl.exists():
            await _cargar_a_s3_con_retry(
                ruta_jsonl,
                f"{settings.s3_prefix}metadata/autocosmos-{fecha_str}-{ruta_jsonl.name}",
            )

        duracion = (datetime.now() - inicio).total_seconds()
        logger.info(
            f"[autocosmos] Scrape finalizado — {len(avisos_validos)} avisos válidos"
            f" listos para carga ({duracion:.1f}s)"
        )
        return avisos_validos









# ─── ENTRYPOINT STANDALONE ───────────────────────────────────────────────────

if __name__ == "__main__":
    from carflip.database.session import AsyncSessionLocal

    logger.remove()
    logger.add(sys.stderr, level=settings.log_level, colorize=True,
               format="<green>{time:HH:mm:ss}</green> | <level>{level: <7}</level> | {message}")
    logger.add(settings.log_file, level="DEBUG", rotation="10 MB", retention="30 days", enqueue=True)

    async def _main() -> None:
        max_paginas = int(sys.argv[1]) if len(sys.argv) > 1 else None
        scraper = ScraperAutocosmosCloud(max_paginas=max_paginas, guardar_raw=True)
        async with AsyncSessionLocal() as sesion:
            resultado = await scraper.ejecutar(sesion)
        logger.info(
            f"[autocosmos] ejecutar() finalizado — {len(resultado.avisos)} avisos,"
            f" {resultado.errores} errores"
        )

    asyncio.run(_main())
