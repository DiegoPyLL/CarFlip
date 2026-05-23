"""
Pipeline cloud completo para Autocosmos Chile.

Etapas cubiertas en scrape():
  1. INGESTA      — paginación HTTP, parseo de cards, descarga de fotos, guardado JSON por página
  2. LIMPIEZA     — deduplicación por id_externo (fotos y JSON)
  3. VALIDACIÓN   — validación estructural y semántica; avisos inválidos van a FAIL LOG
  4. CARGA        — delegada a ScraperBase.ejecutar() vía uploader.upsert_avisos()
"""

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

import httpx
from bs4 import BeautifulSoup, Tag
from fake_useragent import UserAgent
from loguru import logger

from carflip.config import settings
from carflip.database.models import AutocosmosListing
from carflip.scrapers.base import AvisoAuto, ScraperBase
from carflip.scrapers.image_utils import convertir_a_avif
from carflip.storage.s3_cdn import cargar_a_s3_con_retry, url_cdn_desde_clave_s3

BASE_URL = "https://www.autocosmos.cl"
URL_USADOS = f"{BASE_URL}/auto/usado"

_PATRON_AVISO = re.compile(r"^/auto/usado/[^/]+/[^/]+/[^/]+/(\d+)")
_PATRON_FECHA = re.compile(r"^\d{4}-\d{2}-\d{2}$")

_AÑO_MINIMO = 1970
_PRECIO_MINIMO = 500_000
_PRECIO_MAXIMO = 250_000_000

_MAX_REINTENTOS_GET = 10  # reintentos por página antes de saltar a la siguiente

_CONCURRENCIA_PAGINAS = 3   # páginas procesadas en paralelo por lote
_SEM_DESC = 10              # descripciones concurrentes (compartido entre páginas del lote)
_SEM_IMGS = 20              # descargas de imagen concurrentes


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
        _log.debug(f"[autocosmos] {len(avisos)} avisos appended a {ruta_jsonl.name}")
        return True
    except Exception as e:
        _log.error(f"[autocosmos] Error appending avisos a JSONL: {e}")
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
    ext = Path(aviso.url_imagen.split("?")[0]).suffix or ".webp"
    ruta_orig = carpeta_fotos_raw / f"{aviso.id_externo}{ext}"
    if ruta_orig.exists():
        _log.debug(f"[autocosmos] Imagen ya existe: {ruta_orig.name}")
        ruta_avif = carpeta_fotos_processed / f"{aviso.id_externo}.avif"
        return ruta_orig, ruta_avif if ruta_avif.exists() else None
    async with semaforo_imgs:
        try:
            resp = await cliente.get(aviso.url_imagen, headers={"User-Agent": ua.random}, timeout=20.0)
            resp.raise_for_status()
            ruta_orig.write_bytes(resp.content)
        except Exception as e:
            _log.warning(f"[autocosmos] No se pudo descargar imagen id={aviso.id_externo}: {e}")
            return None, None
    # Conversión AVIF en thread pool — es CPU-bound, no debe bloquear el event loop
    ruta_avif = await asyncio.to_thread(convertir_a_avif, ruta_orig, destino=carpeta_fotos_processed)
    if ruta_avif is None:
        fail_logs.append(FailLog(
            etapa="conversion_avif",
            motivo="Conversión AVIF fallida",
            id_externo=aviso.id_externo,
        ))
        _log.debug(f"[autocosmos] Imagen descargada (sin AVIF): id={aviso.id_externo} → {ruta_orig.name}")
    else:
        _log.debug(
            f"[autocosmos] Imagen descargada y convertida:"
            f" id={aviso.id_externo} → raw/{ruta_orig.name}, processed/{ruta_avif.name}"
        )
    return ruta_orig, ruta_avif


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
    _log_i = logger.bind(fase="ingesta")
    if not titulo:
        _log_i.warning(f"[autocosmos] id={id_externo} sin título, usando fallback")
    if precio is None:
        _log_i.warning(f"[autocosmos] id={id_externo} sin precio")
    if km is None:
        _log_i.warning(f"[autocosmos] id={id_externo} km no encontrado")

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



async def _obtener_descripcion(
    cliente: httpx.AsyncClient,
    url: str,
    ua: UserAgent,
    semaforo: asyncio.Semaphore,
) -> str | None:
    async with semaforo:
        try:
            resp = await cliente.get(url, headers={"User-Agent": ua.random}, timeout=20.0)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")
            section = soup.find("section", class_="description")
            if isinstance(section, Tag):
                p = section.select_one("div.grid-container__content p")
                if p:
                    return p.get_text(strip=True) or None
        except Exception as e:
            logger.bind(fase="ingesta").warning(f"[autocosmos] No se pudo obtener descripción de {url}: {e}")
        return None


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

    async def scrape(self) -> list[AvisoAuto]:
        from carflip.scrapers.logging_utils import (
            carpeta_logs_run, configurar_sinks_run, eliminar_sinks,
            log_banner_fase, log_resumen_fase,
        )

        utc_4 = timezone(timedelta(hours=-4))
        inicio = datetime.now(utc_4)

        carpeta_logs = carpeta_logs_run("autocosmos", inicio.replace(tzinfo=None))
        sink_ids = configurar_sinks_run("autocosmos", carpeta_logs)

        log_ingesta   = logger.bind(fase="ingesta")
        log_fotos     = logger.bind(fase="ingesta", tipo="fotos")
        log_meta      = logger.bind(fase="ingesta", tipo="metadata")
        log_limpieza  = logger.bind(fase="limpieza")
        log_validacion = logger.bind(fase="validacion")

        logger.info(f"[autocosmos] Iniciando scrape cloud — {inicio.strftime('%H:%M:%S %d/%m/%Y')}")

        fail_logs: list[FailLog] = []
        avisos_raw: list[AvisoAuto] = []
        vistos_href: set[str] = set()
        paginas_procesadas = 0
        fotos_ok_total = 0
        fotos_total = 0

        fecha_str = inicio.strftime("%H-%M-%S_%d-%m-%Y")
        fecha_dia = inicio.strftime("%Y/%m/%d")
        carpeta = _carpeta_run(Path("autocosmos"), fecha_str) if self.guardar_raw else None
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
            log_banner_fase("autocosmos", 1, "INGESTA")
            t_ingesta = datetime.now()
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as cliente:

                async def _tarea_pagina(pagina: int) -> tuple[list[AvisoAuto], int, int]:
                    """Procesa una página completa. Retorna (avisos, imgs_ok, imgs_total)."""
                    if fin_paginacion.is_set():
                        return [], 0, 0

                    response = None
                    for intento in range(1, _MAX_REINTENTOS_GET + 1):
                        log_ingesta.debug(
                            f"[autocosmos] GET {URL_USADOS} params={{pidx: {pagina}}}"
                            + (f" — intento {intento}/{_MAX_REINTENTOS_GET}" if intento > 1 else "")
                        )
                        try:
                            headers = {"User-Agent": self._ua.random}
                            response = await cliente.get(
                                URL_USADOS, params={"pidx": pagina}, headers=headers
                            )
                            response.raise_for_status()
                            log_ingesta.debug(f"[autocosmos] HTTP {response.status_code} — {response.url}")
                            break
                        except Exception as e:
                            if intento < _MAX_REINTENTOS_GET:
                                log_ingesta.warning(
                                    f"[autocosmos] Error en página {pagina}"
                                    f" intento {intento}/{_MAX_REINTENTOS_GET}: {e} — reintentando en 2s"
                                )
                                await asyncio.sleep(2)
                            else:
                                log_ingesta.error(
                                    f"[autocosmos] Página {pagina}: agotados {_MAX_REINTENTOS_GET}"
                                    f" reintentos, continuando con siguiente página"
                                )

                    if response is None:
                        return [], 0, 0

                    # Parseo HTML en thread pool — CPU-bound, no bloquea el event loop
                    html_text = response.text
                    all_links = await asyncio.to_thread(
                        lambda: BeautifulSoup(html_text, "lxml").find_all("a", href=True)
                    )

                    nuevas_cards: list[Tag] = []
                    async with lock_vistos:
                        for a in all_links:
                            href = str(a.get("href", ""))
                            if _PATRON_AVISO.match(href) and href not in vistos_href:
                                vistos_href.add(href)
                                nuevas_cards.append(a)

                    if not nuevas_cards:
                        log_ingesta.info(f"[autocosmos] Página {pagina}: sin resultados, fin paginación")
                        fin_paginacion.set()
                        return [], 0, 0

                    avisos_pagina: list[AvisoAuto] = []
                    for card in nuevas_cards:
                        try:
                            aviso = _parsear_aviso(card)
                            if aviso:
                                log_ingesta.debug(f"[autocosmos] Parseando aviso id={aviso.id_externo}")
                                avisos_pagina.append(aviso)
                        except Exception as e:
                            log_ingesta.warning(f"[autocosmos] Error parseando card en página {pagina}: {e}")

                    # Fetch descripciones (semáforo compartido entre todas las páginas del lote)
                    if avisos_pagina:
                        tareas_desc = [
                            _obtener_descripcion(cliente, aviso.url, self._ua, sem_desc)
                            for aviso in avisos_pagina
                        ]
                        descripciones = await asyncio.gather(*tareas_desc, return_exceptions=True)
                        for aviso, desc in zip(avisos_pagina, descripciones):
                            aviso.descripcion = desc if isinstance(desc, str) else None
                        desc_ok = sum(1 for d in descripciones if d is not None)
                        log_ingesta.debug(
                            f"[autocosmos] Página {pagina}:"
                            f" {desc_ok}/{len(avisos_pagina)} descripciones obtenidas"
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
                                    clave_raw = f"autocosmos/{fecha_dia}/raw/fotos/{ruta_orig.name}"
                                    tareas_s3_info.append(
                                        (
                                            cargar_a_s3_con_retry(
                                                ruta_orig, clave_raw, etiqueta_log="autocosmos"
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
                                    clave_proc = f"autocosmos/{fecha_dia}/processed/fotos/{ruta_avif.name}"
                                    tareas_s3_info.append(
                                        (
                                            cargar_a_s3_con_retry(
                                                ruta_avif, clave_proc, etiqueta_log="autocosmos"
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
                                f"[autocosmos] Página {pagina}: {imgs_ok_pag}/{imgs_total_pag} imágenes descargadas"
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
                                f"[autocosmos] Página {pagina}: {len(avisos_pagina)} avisos guardados en JSONL"
                            )

                    log_ingesta.debug(f"[autocosmos] Página {pagina}: {len(avisos_pagina)} avisos obtenidos")
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
                            log_ingesta.error(f"[autocosmos] Error inesperado en tarea de página: {resultado}")
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
            log_resumen_fase("autocosmos", "INGESTA", {
                "avisos": len(avisos_raw),
                "páginas": paginas_procesadas,
                "fotos": f"{fotos_ok_total}/{fotos_total}" if fotos_total else "n/a",
                "duración": f"{duracion_ingesta:.0f}s",
            })

            # ── LIMPIEZA (deduplicación por id_externo) ───────────────────────
            log_banner_fase("autocosmos", 2, "LIMPIEZA")
            vistos_id: set[str] = set()
            avisos_unicos: list[AvisoAuto] = []
            for aviso in avisos_raw:
                if aviso.id_externo in vistos_id:
                    log_limpieza.warning(f"[autocosmos] Duplicado detectado id={aviso.id_externo}, descartando")
                    fail_logs.append(FailLog(
                        etapa="dedup_json",
                        motivo="id_externo duplicado entre páginas",
                        id_externo=aviso.id_externo,
                    ))
                else:
                    vistos_id.add(aviso.id_externo)
                    avisos_unicos.append(aviso)

            dups = len(avisos_raw) - len(avisos_unicos)
            log_resumen_fase("autocosmos", "LIMPIEZA", {
                "entrada": len(avisos_raw),
                "únicos": len(avisos_unicos),
                "duplicados": dups,
            })

            # ── VALIDACIÓN ────────────────────────────────────────────────────
            log_banner_fase("autocosmos", 3, "VALIDACIÓN")
            avisos_validos: list[AvisoAuto] = []
            rechazados = 0
            for aviso in avisos_unicos:
                errores = _validar_aviso(aviso)
                if errores:
                    log_validacion.error(f"[autocosmos] Aviso rechazado id={aviso.id_externo}: {errores}")
                    fail_logs.append(FailLog(
                        etapa="validacion_json",
                        motivo="; ".join(errores),
                        id_externo=aviso.id_externo,
                    ))
                    rechazados += 1
                else:
                    avisos_validos.append(aviso)

            log_resumen_fase("autocosmos", "VALIDACIÓN", {
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
                        f"[autocosmos] {len(avisos_validos)} avisos procesados escritos en {ruta_procesados}"
                    )
                else:
                    log_meta.error(f"[autocosmos] Error al escribir avisos procesados en {ruta_procesados}")

            # ── Metadata JSONL raw → S3 ───────────────────────────────────────
            if self.guardar_raw and ruta_jsonl and ruta_jsonl.exists():
                metadata_ok = await cargar_a_s3_con_retry(
                    ruta_jsonl,
                    f"autocosmos/{fecha_dia}/raw/avisos.jsonl",
                    etiqueta_log="autocosmos",
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
                        f"autocosmos/{fecha_dia}/processed/avisos.jsonl",
                        etiqueta_log="autocosmos",
                    )
                    if not processed_ok:
                        fail_logs.append(FailLog(
                            etapa="upload_processed",
                            motivo="S3 upload de processed/avisos.jsonl agotó reintentos",
                            id_externo="avisos.jsonl",
                        ))

            duracion = (datetime.now(utc_4) - inicio).total_seconds()
            logger.info(
                f"[autocosmos] Scrape finalizado — {len(avisos_validos)} avisos válidos"
                f" listos para carga ({duracion:.1f}s)"
            )

            # ── Reporte de ejecución → S3 (siempre, con o sin fallos) ────────
            if self.guardar_raw and carpeta:
                ruta_reporte = carpeta / "processed" / "run_report.json"
                reporte = {
                    "fuente": "autocosmos",
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
                        f"[autocosmos] Reporte escrito — {len(fail_logs)} FAIL LOGs, {duracion:.1f}s"
                    )
                    await cargar_a_s3_con_retry(
                        ruta_reporte,
                        f"autocosmos/{fecha_dia}/logs/run_report.json",
                        etiqueta_log="autocosmos",
                    )
                except Exception as e:
                    log_meta.error(f"[autocosmos] No se pudo escribir run_report.json: {e}")
            elif fail_logs:
                logger.info(
                    f"[autocosmos] {len(fail_logs)} FAIL LOGs generados (guardar_raw=False, no persistidos)"
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
        max_paginas = int(sys.argv[1]) if len(sys.argv) > 1 else None
        scraper = ScraperAutocosmosCloud(max_paginas=max_paginas, guardar_raw=True)
        async with AsyncSessionLocal() as sesion:
            resultado = await scraper.ejecutar(sesion)
        logger.info(
            f"[autocosmos] ejecutar() finalizado — {len(resultado.avisos)} avisos,"
            f" {resultado.errores} errores"
        )

    asyncio.run(_main())
