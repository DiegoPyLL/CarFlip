"""
Pipeline cloud completo para Económicos.cl (grupo El Mercurio).

Etapas cubiertas en scrape():
  1. INGESTA      — paginación ?pagina=N, parseo de cards BS4, enriquecimiento
                    desde la página de detalle (combustible, km, descripción),
                    descarga de fotos
  2. LIMPIEZA     — deduplicación por id_externo
  3. VALIDACIÓN   — validación estructural y semántica; avisos inválidos van a FAIL LOG
  4. CARGA        — delegada a ScraperBase.ejecutar() vía uploader.upsert_avisos()

El listado trae título, precio, ubicación, fecha e imagen; marca, modelo, año,
combustible, km y descripción salen de la página de detalle (sección #specs y
#description). Si el detalle falla, el aviso conserva los datos del listado.
"""

import asyncio
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

import httpx
from bs4 import BeautifulSoup, Tag
from fake_useragent import UserAgent
from loguru import logger

from carflip.config import settings
from carflip.database.models import EconomicosListing
from carflip.scrapers.base import AvisoAuto, ScraperBase, construir_id_externo
from carflip.scrapers.image_utils import convertir_a_avif
from carflip.storage.s3_cdn import cargar_a_s3_con_retry, url_cdn_desde_clave_s3

CODIGO_FUENTE = 105  # identificador único de economicos (ver ScraperBase.codigo_fuente)

BASE_URL = "https://www.economicos.cl"
URL_LISTADO = f"{BASE_URL}/todo_chile/vehiculos"

_PATRON_AVISO = re.compile(r"^/vehiculos/.+-cod\d+\.html$")
_PATRON_FECHA = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_PATRON_KMS = re.compile(r"([\d.,]+)\s*kms?\b", re.IGNORECASE)

_AÑO_MINIMO = 1970
_PRECIO_MINIMO = 500_000
_PRECIO_MAXIMO = 250_000_000

_MAX_REINTENTOS_GET = 10  # reintentos por página antes de saltar a la siguiente

_CONCURRENCIA_PAGINAS = 3   # páginas procesadas en paralelo por lote
_SEM_DESC = 10              # detalles concurrentes (compartido entre páginas del lote)
_SEM_IMGS = 20              # descargas de imagen concurrentes

# El sitio tiene ~500 páginas (~20.000 avisos) ordenadas por fecha descendente.
# Recorrerlo completo no cabe en el presupuesto diario de GitHub Actions, así
# que por defecto se scrapean las primeras _MAX_PAGINAS_DEFAULT (los avisos más
# recientes); el histórico se acumula en la BD run a run.
_MAX_PAGINAS_DEFAULT = 50


# ─── FAIL LOG ────────────────────────────────────────────────────────────────


@dataclass
class FailLog:
    etapa: str
    motivo: str
    id_externo: str
    fuente: str = "economicos"
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
    carpeta = base / fecha_str
    (carpeta / "raw" / "fotos").mkdir(parents=True, exist_ok=True)
    (carpeta / "processed" / "fotos").mkdir(parents=True, exist_ok=True)
    return carpeta


def _aviso_a_dict(aviso: AvisoAuto, foto_local: str | None = None) -> dict:
    return {
        "fuente": aviso.fuente,
        "id_externo": aviso.id_externo,
        "url": aviso.url,
        "titulo": aviso.titulo,
        "precio": int(aviso.precio) if aviso.precio is not None else None,
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
    _log = logger.bind(tipo="metadata")
    try:
        with open(ruta_jsonl, "a", encoding="utf-8") as f:
            for aviso in avisos:
                linea = json.dumps(
                    _aviso_a_dict(aviso, foto_local=fotos.get(aviso.id_externo)),
                    ensure_ascii=False,
                )
                f.write(linea + "\n")
        _log.debug(f"[economicos] {len(avisos)} avisos appended a {ruta_jsonl.name}")
        return True
    except Exception as e:
        _log.error(f"[economicos] Error appending avisos a JSONL: {e}")
        return False


async def _descargar_imagen(
    cliente: httpx.AsyncClient,
    aviso: AvisoAuto,
    carpeta_fotos_raw: Path,
    carpeta_fotos_processed: Path,
    ua: UserAgent,
    fail_logs: list[FailLog],
    semaforo_imgs: asyncio.Semaphore,
) -> tuple[Path | None, Path | None]:
    """Descarga la imagen original a raw/fotos/ y la convierte a AVIF en processed/fotos/."""
    _log = logger.bind(tipo="fotos")
    if not aviso.url_imagen:
        return None, None
    ext = Path(aviso.url_imagen.split("?")[0]).suffix or ".jpg"
    ruta_orig = carpeta_fotos_raw / f"{aviso.id_externo}{ext}"
    if ruta_orig.exists():
        _log.debug(f"[economicos] Imagen ya existe: {ruta_orig.name}")
        ruta_avif = carpeta_fotos_processed / f"{aviso.id_externo}.avif"
        return ruta_orig, ruta_avif if ruta_avif.exists() else None
    async with semaforo_imgs:
        try:
            resp = await cliente.get(aviso.url_imagen, headers={"User-Agent": ua.random}, timeout=20.0)
            resp.raise_for_status()
            ruta_orig.write_bytes(resp.content)
        except Exception as e:
            _log.warning(f"[economicos] No se pudo descargar imagen id={aviso.id_externo}: {e}")
            return None, None
    # Conversión AVIF en thread pool — es CPU-bound, no debe bloquear el event loop
    ruta_avif = await asyncio.to_thread(convertir_a_avif, ruta_orig, destino=carpeta_fotos_processed)
    if ruta_avif is None:
        fail_logs.append(FailLog(
            etapa="conversion_avif",
            motivo="Conversión AVIF fallida",
            id_externo=aviso.id_externo,
        ))
        _log.debug(f"[economicos] Imagen descargada (sin AVIF): id={aviso.id_externo} → {ruta_orig.name}")
    else:
        _log.debug(
            f"[economicos] Imagen descargada y convertida:"
            f" id={aviso.id_externo} → raw/{ruta_orig.name}, processed/{ruta_avif.name}"
        )
    return ruta_orig, ruta_avif


# ─── PARSEO HTML ─────────────────────────────────────────────────────────────


def _parsear_precio(texto: str) -> Decimal | None:
    """Extrae el precio del texto del card (número con puntos, ej. '21.390.000')."""
    match = re.search(r"(\d{1,3}(?:\.\d{3})+|\d{6,})", texto)
    if not match:
        return None
    try:
        return Decimal(match.group(1).replace(".", "").replace(",", ""))
    except InvalidOperation:
        return None


def _parsear_km(texto: str) -> int | None:
    match = _PATRON_KMS.search(texto)
    if not match:
        return None
    try:
        return int(match.group(1).replace(".", "").replace(",", ""))
    except ValueError:
        return None


def _parsear_anio_titulo(titulo: str) -> int | None:
    """El título termina en ' - {año}' (ej. 'Toyota Corolla 2.0 SEG - 2025')."""
    match = re.search(r"-\s*((?:19|20)\d{2})\s*$", titulo)
    if match:
        return int(match.group(1))
    match = re.search(r"\b(19|20)\d{2}\b", titulo)
    return int(match.group(0)) if match else None


def _marca_modelo_desde_titulo(titulo: str) -> tuple[str | None, str | None]:
    """Heurística: las dos primeras palabras del título son marca y modelo."""
    palabras = titulo.strip().split()
    marca = palabras[0].title() if palabras else None
    modelo = palabras[1].title() if len(palabras) > 1 else None
    return marca, modelo


def _parsear_card(tag: Tag) -> AvisoAuto | None:
    """Parsea un card div.result del listado a AvisoAuto."""
    link = tag.find("a", href=True)
    if not isinstance(link, Tag):
        return None
    href = str(link.get("href", ""))
    if not _PATRON_AVISO.match(href):
        return None

    url = urljoin(BASE_URL, href)
    id_externo = construir_id_externo(url)

    h3 = tag.find("h3")
    titulo = h3.get_text(strip=True) if isinstance(h3, Tag) else ""

    precio_tag = tag.find("li", class_="ecn_precio")
    precio = _parsear_precio(precio_tag.get_text(strip=True)) if isinstance(precio_tag, Tag) else None

    ubicacion_tag = tag.find("li", class_="cort_txt")
    ubicacion = ubicacion_tag.get_text(strip=True) if isinstance(ubicacion_tag, Tag) else None

    fecha_publicacion: str | None = None
    time_tag = tag.find("time", class_="timeago")
    if isinstance(time_tag, Tag):
        dt = str(time_tag.get("datetime", ""))
        if len(dt) >= 10:
            fecha_publicacion = dt[:10]

    url_imagen: str | None = None
    img_tag = tag.find("div", class_="delayed-image-load")
    if isinstance(img_tag, Tag):
        data_src = str(img_tag.get("data-src", ""))
        if data_src:
            url_imagen = data_src.split("?")[0]  # sin ?size=150 → imagen completa

    marca, modelo = _marca_modelo_desde_titulo(titulo)
    anio = _parsear_anio_titulo(titulo)

    # Advertencias de ingesta por campos recuperables faltantes
    _log_i = logger.bind(fase="ingesta")
    if not titulo:
        _log_i.warning(f"[economicos] id={id_externo} sin título")
    if precio is None:
        _log_i.warning(f"[economicos] id={id_externo} sin precio")

    return AvisoAuto(
        fuente="economicos",
        id_externo=id_externo,
        url=url,
        titulo=titulo,
        precio=precio,
        moneda="CLP",
        marca=marca,
        modelo=modelo,
        anio=anio,
        ubicacion=ubicacion,
        url_imagen=url_imagen,
        disponible=True,
        fecha_publicacion=fecha_publicacion,
    )


def _parsear_specs_detalle(html: str) -> dict[str, str]:
    """Extrae los pares '<li><span>Campo:</span> valor</li>' de la sección #specs."""
    soup = BeautifulSoup(html, "lxml")
    specs: dict[str, str] = {}
    contenedor = soup.find("div", id="specs")
    ambito = contenedor if isinstance(contenedor, Tag) else soup
    for li in ambito.find_all("li"):
        span = li.find("span")
        if isinstance(span, Tag):
            campo = span.get_text(strip=True).rstrip(":")
            valor = li.get_text(strip=True).replace(span.get_text(strip=True), "", 1).strip()
            if campo and valor:
                specs[campo] = valor
    desc_tag = soup.select_one("#description p")
    if isinstance(desc_tag, Tag):
        specs["_descripcion"] = desc_tag.get_text(strip=True)
    return specs


async def _enriquecer_desde_detalle(
    cliente: httpx.AsyncClient,
    aviso: AvisoAuto,
    ua: UserAgent,
    semaforo: asyncio.Semaphore,
) -> None:
    """Completa combustible, km, descripción, marca/modelo/año desde la página de detalle."""
    async with semaforo:
        try:
            resp = await cliente.get(aviso.url, headers={"User-Agent": ua.random}, timeout=20.0)
            resp.raise_for_status()
        except Exception as e:
            logger.bind(fase="ingesta").warning(
                f"[economicos] No se pudo obtener detalle de {aviso.url}: {e}"
            )
            return

    specs = await asyncio.to_thread(_parsear_specs_detalle, resp.text)

    if marca := specs.get("Marca"):
        aviso.marca = marca.title()
    if modelo := specs.get("Modelo"):
        aviso.modelo = modelo.title()
    if anio_s := specs.get("Año"):
        if anio_s.isdigit():
            aviso.anio = int(anio_s)
    if combustible := specs.get("Combustible"):
        aviso.combustible = combustible
    if fecha := specs.get("Fecha Publicación"):
        if len(fecha) >= 10:
            aviso.fecha_publicacion = fecha[:10]
    if descripcion := specs.get("_descripcion"):
        aviso.descripcion = descripcion
        if aviso.km is None:
            aviso.km = _parsear_km(descripcion)


# ─── SCRAPER CLOUD ────────────────────────────────────────────────────────────


class ScraperEconomicosCloud(ScraperBase):
    """
    Scraper de Económicos.cl con pipeline cloud completo:
    ingesta → limpieza → validación → retorno para carga.
    """

    fuente = "economicos"
    codigo_fuente = CODIGO_FUENTE
    model_class = EconomicosListing

    def __init__(
        self,
        max_paginas: int | None = _MAX_PAGINAS_DEFAULT,
        guardar_raw: bool = True,
    ) -> None:
        self.max_paginas = max_paginas
        self.guardar_raw = guardar_raw
        self._ua = UserAgent()

    async def scrape(self) -> list[AvisoAuto]:
        from carflip.scrapers.logging_utils import (
            carpeta_logs_run, configurar_sinks_run, eliminar_sinks,
            log_banner_fase, log_resumen_fase,
        )

        utc_4 = timezone(timedelta(hours=-4))
        inicio = datetime.now(utc_4)

        carpeta_logs = carpeta_logs_run("economicos", inicio.replace(tzinfo=None))
        sink_ids = configurar_sinks_run("economicos", carpeta_logs)

        log_ingesta   = logger.bind(fase="ingesta")
        log_fotos     = logger.bind(fase="ingesta", tipo="fotos")
        log_meta      = logger.bind(fase="ingesta", tipo="metadata")
        log_limpieza  = logger.bind(fase="limpieza")
        log_validacion = logger.bind(fase="validacion")

        logger.info(f"[economicos] Iniciando scrape cloud — {inicio.strftime('%H:%M:%S %d/%m/%Y')}")

        fail_logs: list[FailLog] = []
        avisos_raw: list[AvisoAuto] = []
        vistos_href: set[str] = set()
        paginas_procesadas = 0
        fotos_ok_total = 0
        fotos_total = 0

        fecha_str = inicio.strftime("%H-%M-%S_%d-%m-%Y")
        fecha_dia = inicio.strftime("%Y/%m/%d")
        carpeta = _carpeta_run(Path("economicos"), fecha_str) if self.guardar_raw else None
        ruta_jsonl = carpeta / "raw" / "avisos.jsonl" if carpeta else None
        carpeta_fotos_raw = carpeta / "raw" / "fotos" if carpeta else None
        carpeta_fotos_processed = carpeta / "processed" / "fotos" if carpeta else None

        lock_vistos = asyncio.Lock()
        lock_jsonl = asyncio.Lock()
        sem_desc = asyncio.Semaphore(_SEM_DESC)
        sem_imgs = asyncio.Semaphore(_SEM_IMGS)
        fin_paginacion = asyncio.Event()

        try:
            # ── INGESTA ──────────────────────────────────────────────────────
            log_banner_fase("economicos", 1, "INGESTA")
            t_ingesta = datetime.now()
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as cliente:

                async def _tarea_pagina(pagina: int) -> tuple[list[AvisoAuto], int, int]:
                    """Procesa una página completa. Retorna (avisos, imgs_ok, imgs_total)."""
                    if fin_paginacion.is_set():
                        return [], 0, 0

                    response = None
                    for intento in range(1, _MAX_REINTENTOS_GET + 1):
                        log_ingesta.debug(
                            f"[economicos] GET {URL_LISTADO} params={{pagina: {pagina}}}"
                            + (f" — intento {intento}/{_MAX_REINTENTOS_GET}" if intento > 1 else "")
                        )
                        try:
                            headers = {"User-Agent": self._ua.random}
                            response = await cliente.get(
                                URL_LISTADO, params={"pagina": pagina}, headers=headers
                            )
                            response.raise_for_status()
                            log_ingesta.debug(f"[economicos] HTTP {response.status_code} — {response.url}")
                            break
                        except Exception as e:
                            if intento < _MAX_REINTENTOS_GET:
                                log_ingesta.warning(
                                    f"[economicos] Error en página {pagina}"
                                    f" intento {intento}/{_MAX_REINTENTOS_GET}: {e} — reintentando en 2s"
                                )
                                await asyncio.sleep(2)
                            else:
                                log_ingesta.error(
                                    f"[economicos] Página {pagina}: agotados {_MAX_REINTENTOS_GET}"
                                    f" reintentos, continuando con siguiente página"
                                )

                    if response is None:
                        return [], 0, 0

                    # Parseo HTML en thread pool — CPU-bound, no bloquea el event loop
                    html_text = response.text
                    cards = await asyncio.to_thread(
                        lambda: BeautifulSoup(html_text, "lxml").find_all("div", class_="result")
                    )

                    nuevas_cards: list[Tag] = []
                    async with lock_vistos:
                        for card in cards:
                            link = card.find("a", href=True)
                            href = str(link.get("href", "")) if isinstance(link, Tag) else ""
                            if _PATRON_AVISO.match(href) and href not in vistos_href:
                                vistos_href.add(href)
                                nuevas_cards.append(card)

                    if not nuevas_cards:
                        log_ingesta.info(f"[economicos] Página {pagina}: sin resultados, fin paginación")
                        fin_paginacion.set()
                        return [], 0, 0

                    avisos_pagina: list[AvisoAuto] = []
                    for card in nuevas_cards:
                        try:
                            aviso = _parsear_card(card)
                            if aviso:
                                log_ingesta.debug(f"[economicos] Parseando aviso id={aviso.id_externo}")
                                avisos_pagina.append(aviso)
                        except Exception as e:
                            log_ingesta.warning(f"[economicos] Error parseando card en página {pagina}: {e}")

                    # Enriquecer desde detalle (semáforo compartido entre páginas del lote)
                    if avisos_pagina:
                        tareas_det = [
                            _enriquecer_desde_detalle(cliente, aviso, self._ua, sem_desc)
                            for aviso in avisos_pagina
                        ]
                        await asyncio.gather(*tareas_det, return_exceptions=True)
                        con_detalle = sum(1 for a in avisos_pagina if a.combustible is not None)
                        log_ingesta.debug(
                            f"[economicos] Página {pagina}:"
                            f" {con_detalle}/{len(avisos_pagina)} detalles obtenidos"
                        )

                    # Descargar fotos con concurrencia controlada por sem_imgs
                    fotos_pagina: dict[str, str] = {}
                    imgs_ok_pag = 0
                    imgs_total_pag = 0
                    if self.guardar_raw and carpeta_fotos_raw and carpeta_fotos_processed and avisos_pagina:
                        tareas_img = [
                            _descargar_imagen(
                                cliente, a, carpeta_fotos_raw, carpeta_fotos_processed,
                                self._ua, fail_logs, sem_imgs,
                            )
                            for a in avisos_pagina
                            if a.url_imagen
                        ]
                        if tareas_img:
                            imgs_total_pag = len(tareas_img)
                            resultados = await asyncio.gather(*tareas_img, return_exceptions=True)
                            avisos_con_imagen = [a for a in avisos_pagina if a.url_imagen]
                            tareas_s3_info: list[tuple] = []  # (coro, aviso, etapa, clave_s3)
                            for aviso, resultado in zip(avisos_con_imagen, resultados):
                                if isinstance(resultado, BaseException):
                                    fail_logs.append(FailLog(
                                        etapa="descarga_foto",
                                        motivo="Excepción descargando imagen",
                                        id_externo=aviso.id_externo,
                                    ))
                                    continue
                                ruta_orig, ruta_avif = resultado
                                if ruta_orig is not None:
                                    fotos_pagina[aviso.id_externo] = ruta_orig.name
                                    clave_raw = f"economicos/{fecha_dia}/raw/fotos/{ruta_orig.name}"
                                    tareas_s3_info.append(
                                        (
                                            cargar_a_s3_con_retry(
                                                ruta_orig, clave_raw, etiqueta_log="economicos",
                                                skip_si_existe=True,
                                            ),
                                            aviso,
                                            "upload_foto_raw",
                                            clave_raw,
                                        )
                                    )
                                else:
                                    fail_logs.append(FailLog(
                                        etapa="descarga_foto",
                                        motivo="Descarga de imagen fallida",
                                        id_externo=aviso.id_externo,
                                    ))
                                if ruta_avif is not None:
                                    clave_proc = f"economicos/{fecha_dia}/processed/fotos/{ruta_avif.name}"
                                    tareas_s3_info.append(
                                        (
                                            cargar_a_s3_con_retry(
                                                ruta_avif, clave_proc, etiqueta_log="economicos",
                                                skip_si_existe=True,
                                            ),
                                            aviso,
                                            "upload_foto_processed",
                                            clave_proc,
                                        )
                                    )
                            imgs_ok_pag = sum(
                                1 for r in resultados if isinstance(r, tuple) and r[0] is not None
                            )
                            imgs_fail = imgs_total_pag - imgs_ok_pag
                            log_fotos.info(
                                f"[economicos] Página {pagina}: {imgs_ok_pag}/{imgs_total_pag} imágenes descargadas"
                                + (f" ({imgs_fail} fallida{'s' if imgs_fail > 1 else ''})" if imgs_fail else "")
                            )
                            if tareas_s3_info:
                                resultados_s3 = await asyncio.gather(*[t[0] for t in tareas_s3_info])
                                for (_, aviso, etapa, clave), s3_ok in zip(tareas_s3_info, resultados_s3):
                                    if not s3_ok:
                                        fail_logs.append(FailLog(
                                            etapa=etapa,
                                            motivo="S3 upload agotó reintentos",
                                            id_externo=aviso.id_externo,
                                        ))
                                    elif etapa == "upload_foto_processed":
                                        if url_cdn := url_cdn_desde_clave_s3(clave):
                                            aviso.url_imagen = url_cdn

                    # Append JSONL con lock para evitar escrituras concurrentes
                    if self.guardar_raw and ruta_jsonl and avisos_pagina:
                        async with lock_jsonl:
                            ok = _append_avisos_jsonl(avisos_pagina, ruta_jsonl, fotos=fotos_pagina)
                        if not ok:
                            for aviso in avisos_pagina:
                                fail_logs.append(FailLog(
                                    etapa="dedup_json",
                                    motivo=f"Error al serializar JSONL página {pagina}",
                                    id_externo=aviso.id_externo,
                                ))
                        else:
                            log_meta.info(
                                f"[economicos] Página {pagina}: {len(avisos_pagina)} avisos guardados en JSONL"
                            )

                    log_ingesta.debug(f"[economicos] Página {pagina}: {len(avisos_pagina)} avisos obtenidos")
                    return avisos_pagina, imgs_ok_pag, imgs_total_pag

                # ── Procesamiento por lotes: _CONCURRENCIA_PAGINAS páginas en paralelo ──
                pagina = 1
                while not fin_paginacion.is_set() and (self.max_paginas is None or pagina <= self.max_paginas):
                    fin_lote = pagina + _CONCURRENCIA_PAGINAS
                    if self.max_paginas is not None:
                        fin_lote = min(fin_lote, self.max_paginas + 1)
                    nums_lote = list(range(pagina, fin_lote))

                    resultados_lote = await asyncio.gather(
                        *[_tarea_pagina(p) for p in nums_lote],
                        return_exceptions=True,
                    )

                    for resultado in resultados_lote:
                        if isinstance(resultado, BaseException):
                            log_ingesta.error(f"[economicos] Error inesperado en tarea de página: {resultado}")
                            continue
                        avisos_p, imgs_ok, imgs_t = resultado
                        if avisos_p:
                            avisos_raw.extend(avisos_p)
                            paginas_procesadas += 1
                        fotos_ok_total += imgs_ok
                        fotos_total += imgs_t

                    pagina += _CONCURRENCIA_PAGINAS
                    if not fin_paginacion.is_set():
                        await self.espera_aleatoria()

            duracion_ingesta = (datetime.now() - t_ingesta).total_seconds()
            log_resumen_fase("economicos", "INGESTA", {
                "avisos": len(avisos_raw),
                "páginas": paginas_procesadas,
                "fotos": f"{fotos_ok_total}/{fotos_total}" if fotos_total else "n/a",
                "duración": f"{duracion_ingesta:.0f}s",
            })

            # ── LIMPIEZA (deduplicación por id_externo) ───────────────────────
            log_banner_fase("economicos", 2, "LIMPIEZA")
            vistos_id: set[str] = set()
            avisos_unicos: list[AvisoAuto] = []
            for aviso in avisos_raw:
                if aviso.id_externo in vistos_id:
                    log_limpieza.warning(f"[economicos] Duplicado detectado id={aviso.id_externo}, descartando")
                    fail_logs.append(FailLog(
                        etapa="dedup_json",
                        motivo="id_externo duplicado entre páginas",
                        id_externo=aviso.id_externo,
                    ))
                else:
                    vistos_id.add(aviso.id_externo)
                    avisos_unicos.append(aviso)

            dups = len(avisos_raw) - len(avisos_unicos)
            log_resumen_fase("economicos", "LIMPIEZA", {
                "entrada": len(avisos_raw),
                "únicos": len(avisos_unicos),
                "duplicados": dups,
            })

            # ── VALIDACIÓN ────────────────────────────────────────────────────
            log_banner_fase("economicos", 3, "VALIDACIÓN")
            avisos_validos: list[AvisoAuto] = []
            rechazados = 0
            for aviso in avisos_unicos:
                errores = _validar_aviso(aviso)
                if errores:
                    log_validacion.error(f"[economicos] Aviso rechazado id={aviso.id_externo}: {errores}")
                    fail_logs.append(FailLog(
                        etapa="validacion_json",
                        motivo="; ".join(errores),
                        id_externo=aviso.id_externo,
                    ))
                    rechazados += 1
                else:
                    avisos_validos.append(aviso)

            log_resumen_fase("economicos", "VALIDACIÓN", {
                "válidos": len(avisos_validos),
                "rechazados": rechazados,
                "total": len(avisos_unicos),
            })

            # ── PROCESADOS (limpieza + validación superada) ──────────────────
            if self.guardar_raw and avisos_validos and carpeta:
                carpeta_procesados = carpeta / "processed"
                ruta_procesados = carpeta_procesados / "avisos.jsonl"
                ok = _append_avisos_jsonl(avisos_validos, ruta_procesados)
                if ok:
                    log_meta.info(
                        f"[economicos] {len(avisos_validos)} avisos procesados escritos en {ruta_procesados}"
                    )
                else:
                    log_meta.error(f"[economicos] Error al escribir avisos procesados en {ruta_procesados}")

            # ── Metadata JSONL raw → S3 ───────────────────────────────────────
            if self.guardar_raw and ruta_jsonl and ruta_jsonl.exists():
                metadata_ok = await cargar_a_s3_con_retry(
                    ruta_jsonl,
                    f"economicos/{fecha_dia}/raw/avisos.jsonl",
                    etiqueta_log="economicos",
                )
                if not metadata_ok:
                    fail_logs.append(FailLog(
                        etapa="upload_metadata",
                        motivo="S3 upload de raw/avisos.jsonl agotó reintentos",
                        id_externo="avisos.jsonl",
                    ))

            # ── Processed JSONL → S3 ─────────────────────────────────────────
            if self.guardar_raw and avisos_validos and carpeta:
                ruta_procesados_jsonl = carpeta / "processed" / "avisos.jsonl"
                if ruta_procesados_jsonl.exists():
                    processed_ok = await cargar_a_s3_con_retry(
                        ruta_procesados_jsonl,
                        f"economicos/{fecha_dia}/processed/avisos.jsonl",
                        etiqueta_log="economicos",
                    )
                    if not processed_ok:
                        fail_logs.append(FailLog(
                            etapa="upload_processed",
                            motivo="S3 upload de processed/avisos.jsonl agotó reintentos",
                            id_externo="avisos.jsonl",
                        ))

            duracion = (datetime.now(utc_4) - inicio).total_seconds()
            logger.info(
                f"[economicos] Scrape finalizado — {len(avisos_validos)} avisos válidos"
                f" listos para carga ({duracion:.1f}s)"
            )

            # ── Reporte de ejecución → S3 (siempre, con o sin fallos) ────────
            if self.guardar_raw and carpeta:
                ruta_reporte = carpeta / "processed" / "run_report.json"
                reporte = {
                    "fuente": "economicos",
                    "timestamp": inicio.isoformat(),
                    "duracion_segundos": round(duracion, 1),
                    "paginas_procesadas": paginas_procesadas,
                    "avisos_encontrados": len(avisos_raw),
                    "avisos_unicos": len(avisos_unicos),
                    "avisos_validos": len(avisos_validos),
                    "avisos_rechazados": len(avisos_unicos) - len(avisos_validos),
                    "fail_logs": [asdict(fl) for fl in fail_logs],
                }
                try:
                    ruta_reporte.write_text(
                        json.dumps(reporte, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                    log_meta.info(
                        f"[economicos] Reporte escrito — {len(fail_logs)} FAIL LOGs, {duracion:.1f}s"
                    )
                    await cargar_a_s3_con_retry(
                        ruta_reporte,
                        f"economicos/{fecha_dia}/logs/run_report.json",
                        etiqueta_log="economicos",
                    )
                except Exception as e:
                    log_meta.error(f"[economicos] No se pudo escribir run_report.json: {e}")
            elif fail_logs:
                logger.info(
                    f"[economicos] {len(fail_logs)} FAIL LOGs generados (guardar_raw=False, no persistidos)"
                )

            return avisos_validos

        finally:
            eliminar_sinks(sink_ids)


# ─── ENTRYPOINT STANDALONE ───────────────────────────────────────────────────

if __name__ == "__main__":
    from carflip.database.session import AsyncSessionLocal

    logger.remove()
    logger.add(sys.stderr, level=settings.log_level, colorize=True,
               format="<green>{time:HH:mm:ss}</green> | <level>{level: <7}</level> | {message}")
    logger.add(settings.log_file, level="DEBUG", rotation="10 MB", retention="30 days", enqueue=True)

    async def _main() -> None:
        max_paginas = int(sys.argv[1]) if len(sys.argv) > 1 else _MAX_PAGINAS_DEFAULT
        scraper = ScraperEconomicosCloud(max_paginas=max_paginas, guardar_raw=True)
        async with AsyncSessionLocal() as sesion:
            resultado = await scraper.ejecutar(sesion)
        logger.info(
            f"[economicos] ejecutar() finalizado — {len(resultado.avisos)} avisos,"
            f" {resultado.errores} errores"
        )

    asyncio.run(_main())
