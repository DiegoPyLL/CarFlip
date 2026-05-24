"""
Pipeline cloud completo para Yapo Chile.

Etapas cubiertas en scrape():
  1. INGESTA      — navegación Playwright, extracción JS, descarga de fotos, guardado JSON por aviso
  2. LIMPIEZA     — deduplicación por id_externo
  3. VALIDACIÓN   — validación estructural y semántica; avisos inválidos van a FAIL LOG
  4. CARGA        — delegada a ScraperBase.ejecutar() vía uploader.upsert_avisos()
"""

import asyncio
import hashlib
import json
import random
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlparse

import httpx
from loguru import logger
from playwright.async_api import async_playwright

from carflip.config import settings
from carflip.database.models import YapoListing
from carflip.scrapers.base import (
    AvisoAuto,
    ScraperBase,
    construir_id_externo,
    normalizar_url,
)
from carflip.scrapers.image_utils import convertir_a_avif
from carflip.storage.s3_cdn import cargar_a_s3_con_retry, cliente_s3, url_cdn_desde_clave_s3

CODIGO_FUENTE = 101  # identificador único de yapo (ver ScraperBase.codigo_fuente)

YAPO_BASE = "https://www.yapo.cl"
_AÑO_MINIMO = 1970
_PRECIO_MINIMO = 500_000
_PRECIO_MAXIMO = 250_000_000
_PATRON_FECHA = re.compile(r"^\d{4}-\d{2}-\d{2}$")

_MAX_AVISOS = 1_000

_CONCURRENCIA_DETALLES = 1   # páginas de detalle procesadas en paralelo (Playwright)
_SEM_IMGS = 20               # descargas de imagen concurrentes

_GOTO_MAX_INTENTOS = 3       # reintentos de navegación por página de detalle
_GOTO_BACKOFF_BASE = 3.0     # backoff entre reintentos: BASE * intento + jitter(0..1)

_LOTE_UPSERT    = 50         # avisos por lote antes de subir a BD
_LOTE_PAUSA     = 100        # avisos procesados antes de pausar
_PAUSA_LOTE_SEG = 300        # 5 minutos de pausa entre lotes de 100

_THROTTLE_MIN = 0.3          # delay jittered antes de navegar (espaciar/desincronizar)
_THROTTLE_MAX = 1.2

_HEADERS_HTTP = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": YAPO_BASE,
}


def _id_nativo_yapo(url: str) -> str:
    """ID nativo de Yapo: último segmento numérico del path. Fallback a hash estable."""
    ultimo = urlparse(url).path.rstrip("/").rsplit("/", 1)[-1]
    if ultimo.isdigit():
        return ultimo
    return hashlib.sha256(normalizar_url(url).encode()).hexdigest()[:16]


# ─── FAIL LOG ────────────────────────────────────────────────────────────────


@dataclass
class FailLog:
    etapa: str
    motivo: str
    id_externo: str
    fuente: str = "yapo"
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ─── VALIDACIÓN ──────────────────────────────────────────────────────────────


def _validar_aviso(aviso: AvisoAuto) -> list[str]:
    """Retorna lista de errores. Lista vacía = aviso válido."""
    errores: list[str] = []
    anio_actual = datetime.now().year

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
                f = datetime.strptime(aviso.fecha_publicacion, "%Y-%m-%d").date()
                if f > datetime.now().date():
                    errores.append(f"fecha_publicacion es futura: {aviso.fecha_publicacion}")
            except ValueError:
                errores.append(f"fecha_publicacion inválida: {aviso.fecha_publicacion!r}")

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
        _log.debug(f"[yapo] {len(avisos)} avisos appended a {ruta_jsonl.name}")
        return True
    except Exception as e:
        _log.error(f"[yapo] Error appending avisos a JSONL: {e}")
        return False


# ─── SCRAPER CLOUD ────────────────────────────────────────────────────────────


class ScraperYapoCloud(ScraperBase):
    fuente = "yapo"
    codigo_fuente = CODIGO_FUENTE
    model_class = YapoListing

    _JS_ATTRS = """() => {
        const dls = document.querySelectorAll('.d3-property-insight__attribute-details');
        const out = {};
        for (const dl of dls) {
            const dts = dl.querySelectorAll('dt');
            const dds = dl.querySelectorAll('dd');
            for (let i = 0; i < dts.length; i++) {
                out[dts[i].innerText.trim()] = dds[i] ? dds[i].innerText.trim() : '';
            }
        }
        for (const s of document.querySelectorAll('script[type="application/ld+json"]')) {
            try {
                const d = JSON.parse(s.textContent);
                if (d['@type'] === 'Car') {
                    if (d.vehicleTransmission && !out['Transmision']) out['Transmision'] = d.vehicleTransmission;
                    if (d.fuelType && !out['Combustible']) out['Combustible'] = d.fuelType;
                    if (d.mileageFromOdometer && !out['Kilometros']) out['Kilometros'] = String(d.mileageFromOdometer.value || '');
                    if (d.modelDate && !out['Ano']) out['Ano'] = String(d.modelDate);
                }
            } catch(e) {}
        }
        out['imagen_url'] = '';
        for (const img of document.querySelectorAll(
            '.d3-gallery img, .d3-photos-carousel img, [class*="gallery"] img, [class*="photo"] img'
        )) {
            const src = img.src || img.dataset.src || '';
            if (src && src.startsWith('http') && src.includes('t_or_fh')) {
                out['imagen_url'] = src;
                break;
            }
        }
        return out;
    }"""

    def __init__(self, max_paginas: int | None = None, guardar_raw: bool = True) -> None:
        self.max_paginas = max_paginas
        self.guardar_raw = guardar_raw

    def _get_attr(self, attrs: dict, *claves: str) -> str:
        import unicodedata

        def norm(s: str) -> str:
            return unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode().lower()

        for clave in claves:
            for k, v in attrs.items():
                if norm(k) == norm(clave) and v:
                    return v
        return ""

    def _limpiar_km(self, texto: str) -> int | None:
        solo = re.sub(r"[.'`,\s]", "", texto)
        return int(solo) if solo.isdigit() else None

    def _limpiar_precio(self, texto: str) -> int | None:
        linea = texto.split("\n")[0]
        solo = re.sub(r"[^\d]", "", linea)
        return int(solo) if solo else None

    def _normalizar_combustible(self, valor: str) -> str | None:
        v = valor.lower().strip()
        if any(w in v for w in ["eléctrico", "electrico", "electric", "ev"]): return "electrico"
        if any(w in v for w in ["híbrido", "hibrido", "hybrid"]): return "hibrido"
        if any(w in v for w in ["diesel", "diésel"]): return "diesel"
        if any(w in v for w in ["bencina", "gasolina", "nafta"]): return "bencina"
        return v if v else None

    async def _descargar_imagen(
        self,
        cliente_http: httpx.AsyncClient,
        url: str,
        ruta_raw: Path,
        carpeta_processed: Path,
        fail_logs: list[FailLog],
        aviso_id: str,
        sem_imgs: asyncio.Semaphore,
    ) -> tuple[Path | None, Path | None]:
        """Descarga la imagen original a raw/fotos/ y la convierte a AVIF en processed/fotos/."""
        _log = logger.bind(tipo="fotos")
        if not url:
            return None, None
        if ruta_raw.exists():
            ruta_avif = carpeta_processed / f"{ruta_raw.stem}.avif"
            return ruta_raw, ruta_avif if ruta_avif.exists() else None
        async with sem_imgs:
            try:
                resp = await cliente_http.get(url, headers=_HEADERS_HTTP, timeout=15)
                resp.raise_for_status()
                ruta_raw.write_bytes(resp.content)
            except Exception as e:
                _log.warning(f"[yapo] No se pudo descargar imagen {ruta_raw.name}: {e}")
                return None, None
        # Conversión AVIF en thread pool — CPU-bound, no debe bloquear el event loop
        ruta_avif = await asyncio.to_thread(convertir_a_avif, ruta_raw, destino=carpeta_processed)
        if ruta_avif is None:
            fail_logs.append(FailLog(
                etapa="conversion_avif",
                motivo="Conversión AVIF fallida",
                id_externo=aviso_id,
            ))
            _log.debug(f"[yapo] Imagen descargada (sin AVIF): id={aviso_id} → {ruta_raw.name}")
        else:
            _log.debug(
                f"[yapo] Imagen descargada y convertida a AVIF:"
                f" id={aviso_id} → raw/{ruta_raw.name}, processed/{ruta_avif.name}"
            )
        return ruta_raw, ruta_avif

    async def scrape(self) -> list[AvisoAuto]:
        from carflip.scrapers.logging_utils import (
            carpeta_logs_run, configurar_sinks_run, eliminar_sinks,
            log_banner_fase, log_resumen_fase,
        )

        utc_4 = timezone(timedelta(hours=-4))
        inicio = datetime.now(utc_4)

        carpeta_logs = carpeta_logs_run("yapo", inicio.replace(tzinfo=None))
        sink_ids = configurar_sinks_run("yapo", carpeta_logs)

        log_ingesta    = logger.bind(fase="ingesta")
        log_fotos      = logger.bind(fase="ingesta", tipo="fotos")
        log_meta       = logger.bind(fase="ingesta", tipo="metadata")
        log_limpieza   = logger.bind(fase="limpieza")
        log_validacion = logger.bind(fase="validacion")

        logger.info(f"[yapo] Iniciando scrape cloud — {inicio.strftime('%H:%M:%S %d/%m/%Y')}")

        fecha_str = inicio.strftime("%H-%M-%S_%d-%m-%Y")
        fecha_dia = inicio.strftime("%Y/%m/%d")
        carpeta = (Path("yapo") / fecha_str) if self.guardar_raw else None
        if carpeta:
            (carpeta / "raw" / "fotos").mkdir(parents=True, exist_ok=True)
            (carpeta / "processed" / "fotos").mkdir(parents=True, exist_ok=True)
        ruta_jsonl = carpeta / "raw" / "avisos.jsonl" if carpeta else None
        carpeta_fotos_raw = carpeta / "raw" / "fotos" if carpeta else None
        carpeta_fotos_processed = carpeta / "processed" / "fotos" if carpeta else None

        fail_logs: list[FailLog] = []
        avisos_raw: list[AvisoAuto] = []
        avisos_validos: list[AvisoAuto] = []
        vistos_dedup_id: set[str] = set()
        rechazados_total = 0
        dups_total = 0
        fotos_run: dict[str, str] = {}
        fotos_ok_total = 0
        fotos_total = 0
        vistos_urls: set[str] = set()
        lock_vistos_urls = asyncio.Lock()
        avisos_info = []

        try:
            # ── INGESTA ──────────────────────────────────────────────────────
            log_banner_fase("yapo", 1, "INGESTA")
            t_ingesta = datetime.now()

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
                ctx = await browser.new_context(
                    user_agent=_HEADERS_HTTP["User-Agent"],
                    viewport={"width": 1280, "height": 800},
                    locale="es-CL",
                )
                page = await ctx.new_page()
                await page.route("**/*.{png,jpg,jpeg,gif,webp,svg,woff,woff2,ttf,otf}", lambda route: route.abort())

                # ── INGESTA: listado ──────────────────────────────────────────
                pagina = 0
                while True:
                    pagina += 1
                    if self.max_paginas and pagina > self.max_paginas:
                        break
                    url = f"{YAPO_BASE}/autos-usados.{pagina}"
                    log_ingesta.info(f"[yapo] Listado página {pagina}: {url}")
                    try:
                        await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                        await page.wait_for_selector("div.d3-ads-grid", timeout=20_000)
                    except Exception as e:
                        log_ingesta.warning(f"[yapo] Timeout en página {pagina}: {e}")
                        break

                    await page.wait_for_timeout(2_000)
                    cards = await page.query_selector_all("div.d3-ad-tile")
                    if not cards:
                        log_ingesta.info(f"[yapo] Página {pagina}: sin resultados, fin paginación")
                        break

                    count_antes = len(avisos_info)
                    for card in cards:
                        link = await card.query_selector("a[href^='/autos-usados']")
                        if not link:
                            continue
                        href = await link.get_attribute("href")
                        if not href:
                            continue

                        url_aviso = YAPO_BASE + href
                        async with lock_vistos_urls:
                            if url_aviso in vistos_urls:
                                continue
                            vistos_urls.add(url_aviso)

                        async def _safe(sel: str) -> str:
                            try:
                                n = await card.query_selector(sel)
                                return (await n.inner_text()).strip() if n else ""
                            except Exception:
                                return ""

                        # Extraer fecha desde atributo datetime del elemento time
                        # (inner_text() retorna "hace 2 días", no YYYY-MM-DD)
                        fecha_card = datetime.now().strftime("%Y-%m-%d")
                        time_el = await card.query_selector("time[datetime]")
                        if time_el:
                            dt_attr = await time_el.get_attribute("datetime") or ""
                            if re.match(r"^\d{4}-\d{2}-\d{2}", dt_attr):
                                fecha_card = dt_attr[:10]

                        avisos_info.append({
                            "url": url_aviso,
                            "precio": await _safe("[class*='d3-ad-tile__price']"),
                            "region": await _safe("[class*='d3-ad-tile__location']"),
                            "fecha": fecha_card,
                        })

                    nuevos = len(avisos_info) - count_antes
                    log_ingesta.info(f"[yapo] Página {pagina}: {nuevos} URLs recolectadas (total {len(avisos_info)})")

                    if len(avisos_info) >= _MAX_AVISOS:
                        avisos_info = avisos_info[:_MAX_AVISOS]
                        log_ingesta.info(f"[yapo] Límite de {_MAX_AVISOS} publicaciones alcanzado, deteniendo paginación")
                        break

                # ── INGESTA: detalles (pool de _CONCURRENCIA_DETALLES páginas en paralelo) ──
                sem_detalles = asyncio.Semaphore(_CONCURRENCIA_DETALLES)
                sem_imgs = asyncio.Semaphore(_SEM_IMGS)
                lock_jsonl = asyncio.Lock()
                total_avisos = len(avisos_info)

                async with httpx.AsyncClient() as cliente_http, cliente_s3() as s3:
                    async def _tarea_detalle(info: dict, idx: int) -> AvisoAuto | None:
                        nonlocal fotos_ok_total, fotos_total
                        url_det = info["url"]
                        aviso_id = construir_id_externo(url_det)

                        async with sem_detalles:
                            # Throttle jittered: espaciar/desincronizar navegaciones concurrentes
                            # (anti-bot de Yapo + EC2 burstable: dormir aquí también baja la presión
                            # de CPU, dando margen a que se recuperen los créditos).
                            await asyncio.sleep(random.uniform(_THROTTLE_MIN, _THROTTLE_MAX))
                            p = await ctx.new_page()
                            await p.route(
                                "**/*.{png,jpg,jpeg,gif,webp,svg,woff,woff2,ttf,otf}",
                                lambda route: route.abort(),
                            )
                            try:
                                log_ingesta.debug(f"[yapo] Detalle {idx}/{total_avisos}: {url_det}")
                                # Retry con backoff: un timeout aislado ya no descarta el aviso, y el
                                # sleep entre intentos deja respirar al sitio y a la CPU del EC2.
                                attrs = None
                                for intento in range(1, _GOTO_MAX_INTENTOS + 1):
                                    try:
                                        await p.goto(url_det, wait_until="domcontentloaded", timeout=25_000)
                                        await p.wait_for_timeout(1_500)
                                        attrs = await p.evaluate(self._JS_ATTRS)
                                        break
                                    except Exception as e:
                                        if intento < _GOTO_MAX_INTENTOS:
                                            backoff = _GOTO_BACKOFF_BASE * intento + random.uniform(0, 1)
                                            log_ingesta.warning(
                                                f"[yapo] goto fallido id={aviso_id}"
                                                f" intento {intento}/{_GOTO_MAX_INTENTOS}: {e}."
                                                f" Reintentando en {backoff:.1f}s"
                                            )
                                            await asyncio.sleep(backoff)
                                        else:
                                            log_ingesta.error(
                                                f"[yapo] Error cargando detalle id={aviso_id}"
                                                f" tras {_GOTO_MAX_INTENTOS} intentos: {e}"
                                            )
                                            fail_logs.append(FailLog(etapa="ingesta", motivo=str(e), id_externo=aviso_id))
                                            return None

                                km_raw = self._get_attr(attrs, "Kilómetros", "Kilometros", "Kilometraje")
                                precio_raw = self._limpiar_precio(info["precio"])
                                km = self._limpiar_km(km_raw) if km_raw else None
                                anio_s = self._get_attr(attrs, "Año", "Ano")
                                anio = int(anio_s) if anio_s.isdigit() else None
                                marca = self._get_attr(attrs, "Marca") or None
                                modelo = self._get_attr(attrs, "Modelo") or None
                                img_url = attrs.get("imagen_url", "") or None

                                log_ingesta.debug(f"[yapo] Parseando aviso id={aviso_id}")
                                if precio_raw is None:
                                    log_ingesta.warning(f"[yapo] id={aviso_id} sin precio")
                                if km is None:
                                    log_ingesta.warning(f"[yapo] id={aviso_id} km no encontrado")
                                if not marca and not modelo:
                                    log_ingesta.warning(f"[yapo] id={aviso_id} sin marca ni modelo, título con fallback")

                                av_auto = AvisoAuto(
                                    fuente=self.fuente,
                                    id_externo=aviso_id,
                                    url=url_det,
                                    titulo=f"{marca or ''} {modelo or ''} {anio_s} usado precio {info['precio'].split(chr(10))[0]}".strip(),
                                    precio=Decimal(precio_raw) if precio_raw is not None else None,
                                    moneda="CLP",
                                    marca=marca,
                                    modelo=modelo,
                                    anio=anio,
                                    km=km,
                                    ubicacion=info["region"] or None,
                                    combustible=self._normalizar_combustible(self._get_attr(attrs, "Combustible")),
                                    url_imagen=img_url,
                                    disponible=True,
                                    fecha_publicacion=info["fecha"],
                                )

                                if self.guardar_raw and carpeta_fotos_raw and carpeta_fotos_processed and img_url:
                                    ruta_foto_raw = carpeta_fotos_raw / f"{aviso_id}.jpg"
                                    fotos_total += 1
                                    ruta_orig, ruta_avif = await self._descargar_imagen(
                                        cliente_http, img_url, ruta_foto_raw,
                                        carpeta_fotos_processed, fail_logs, aviso_id, sem_imgs,
                                    )
                                    if ruta_orig is not None:
                                        fotos_ok_total += 1
                                        fotos_run[aviso_id] = ruta_orig.name
                                        log_fotos.info(f"[yapo] [{idx}/{total_avisos}] Foto descargada id={aviso_id}")
                                        clave_raw = f"yapo/raw/fotos/{ruta_orig.name}"
                                        tareas_s3: list[tuple] = [
                                            (
                                                cargar_a_s3_con_retry(
                                                    ruta_orig, clave_raw, etiqueta_log="yapo",
                                                    skip_si_existe=True, cliente=s3,
                                                ),
                                                "upload_foto_raw",
                                                None,
                                            )
                                        ]
                                        clave_avif: str | None = None
                                        if ruta_avif is not None:
                                            clave_avif = (
                                                f"yapo/processed/fotos/{ruta_avif.name}"
                                            )
                                            tareas_s3.append(
                                                (
                                                    cargar_a_s3_con_retry(
                                                        ruta_avif, clave_avif, etiqueta_log="yapo",
                                                        skip_si_existe=True, cliente=s3,
                                                    ),
                                                    "upload_foto_processed",
                                                    clave_avif,
                                                )
                                            )
                                        s3_res = await asyncio.gather(*[t[0] for t in tareas_s3])
                                        for (_, etapa, clave), s3_ok in zip(tareas_s3, s3_res):
                                            if not s3_ok:
                                                fail_logs.append(FailLog(
                                                    etapa=etapa,
                                                    motivo="S3 upload de imagen agotó reintentos",
                                                    id_externo=aviso_id,
                                                ))
                                            elif etapa == "upload_foto_processed" and clave:
                                                if url_cdn := url_cdn_desde_clave_s3(clave):
                                                    av_auto.url_imagen = url_cdn
                                    else:
                                        log_fotos.warning(f"[yapo] [{idx}/{total_avisos}] Foto fallida id={aviso_id}")
                                        fail_logs.append(FailLog(etapa="descarga_foto", motivo="Descarga de imagen fallida", id_externo=aviso_id))

                                if self.guardar_raw and ruta_jsonl:
                                    async with lock_jsonl:
                                        ok = _append_avisos_jsonl([av_auto], ruta_jsonl, fotos=fotos_run)
                                    if not ok:
                                        fail_logs.append(FailLog(etapa="dedup_json", motivo="Error al serializar JSONL", id_externo=aviso_id))
                                    else:
                                        log_meta.info(f"[yapo] [{idx}/{total_avisos}] Metadata guardada id={aviso_id}")

                                return av_auto
                            finally:
                                await p.close()

                    async def _upsert_parcial(lote_validos: list[AvisoAuto]) -> None:
                        if not lote_validos or self.model_class is None:
                            return
                        from carflip.database.session import AsyncSessionLocal
                        from carflip.database.uploader import upsert_avisos
                        try:
                            async with AsyncSessionLocal() as sesion_lote:
                                n = await upsert_avisos(sesion_lote, lote_validos, self.model_class)
                                logger.info(f"[yapo] Upsert parcial: {n} avisos subidos a BD")
                        except Exception as e:
                            logger.error(f"[yapo] Error en upsert parcial: {e}")

                    for lote_inicio in range(0, total_avisos, _LOTE_UPSERT):
                        lote_infos = avisos_info[lote_inicio : lote_inicio + _LOTE_UPSERT]
                        tareas_lote = [
                            _tarea_detalle(info, lote_inicio + i + 1)
                            for i, info in enumerate(lote_infos)
                        ]
                        resultados_lote = await asyncio.gather(*tareas_lote, return_exceptions=True)

                        lote_raw: list[AvisoAuto] = []
                        for resultado in resultados_lote:
                            if isinstance(resultado, BaseException):
                                log_ingesta.error(f"[yapo] Error inesperado en tarea de detalle: {resultado}")
                            elif resultado is not None:
                                avisos_raw.append(resultado)
                                lote_raw.append(resultado)

                        # Deduplicación incremental del lote
                        lote_unicos: list[AvisoAuto] = []
                        for av in lote_raw:
                            if av.id_externo in vistos_dedup_id:
                                log_limpieza.warning(f"[yapo] Duplicado detectado id={av.id_externo}, descartando")
                                fail_logs.append(FailLog(
                                    etapa="dedup_json",
                                    motivo="id_externo duplicado entre páginas",
                                    id_externo=av.id_externo,
                                ))
                                dups_total += 1
                            else:
                                vistos_dedup_id.add(av.id_externo)
                                lote_unicos.append(av)

                        # Validación incremental del lote
                        lote_validos: list[AvisoAuto] = []
                        for av in lote_unicos:
                            errores = _validar_aviso(av)
                            if errores:
                                log_validacion.error(f"[yapo] Aviso rechazado id={av.id_externo}: {errores}")
                                fail_logs.append(FailLog(
                                    etapa="validacion_json",
                                    motivo="; ".join(errores),
                                    id_externo=av.id_externo,
                                ))
                                rechazados_total += 1
                            else:
                                lote_validos.append(av)

                        # Upsert parcial del lote a BD
                        n_procesados = lote_inicio + len(lote_infos)
                        log_ingesta.info(
                            f"[yapo] Lote {lote_inicio // _LOTE_UPSERT + 1}: "
                            f"{len(lote_validos)}/{len(lote_infos)} válidos "
                            f"(procesados: {n_procesados}/{total_avisos})"
                        )
                        await _upsert_parcial(lote_validos)
                        avisos_validos.extend(lote_validos)

                        # Pausa cada _LOTE_PAUSA publicaciones procesadas
                        es_ultimo = n_procesados >= total_avisos
                        if not es_ultimo and n_procesados % _LOTE_PAUSA == 0:
                            logger.info(
                                f"[yapo] {n_procesados} avisos procesados — "
                                f"pausa de {_PAUSA_LOTE_SEG // 60} min antes del siguiente lote"
                            )
                            await asyncio.sleep(_PAUSA_LOTE_SEG)

                await ctx.close()
                await browser.close()

            duracion_ingesta = (datetime.now() - t_ingesta).total_seconds()
            log_resumen_fase("yapo", "INGESTA", {
                "avisos": len(avisos_raw),
                "válidos": len(avisos_validos),
                "duplicados": dups_total,
                "rechazados": rechazados_total,
                "fotos": f"{fotos_ok_total}/{fotos_total}" if fotos_total else "n/a",
                "duración": f"{duracion_ingesta:.0f}s",
            })

            # ── PROCESADOS (limpieza + validación superada) ──────────────────
            if self.guardar_raw and avisos_validos and carpeta:
                ruta_procesados = carpeta / "processed" / "avisos.jsonl"
                ok = _append_avisos_jsonl(avisos_validos, ruta_procesados, fotos=fotos_run)
                if ok:
                    log_meta.info(
                        f"[yapo] {len(avisos_validos)} avisos procesados escritos en {ruta_procesados}"
                    )
                else:
                    log_meta.error(f"[yapo] Error al escribir avisos procesados en {ruta_procesados}")

            # ── Metadata JSONL raw → S3 ───────────────────────────────────────
            if self.guardar_raw and ruta_jsonl and ruta_jsonl.exists():
                metadata_ok = await cargar_a_s3_con_retry(
                    ruta_jsonl,
                    f"yapo/{fecha_dia}/raw/avisos.jsonl",
                    etiqueta_log="yapo",
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
                        f"yapo/{fecha_dia}/processed/avisos.jsonl",
                        etiqueta_log="yapo",
                    )
                    if not processed_ok:
                        fail_logs.append(FailLog(
                            etapa="upload_processed",
                            motivo="S3 upload de processed/avisos.jsonl agotó reintentos",
                            id_externo="avisos.jsonl",
                        ))

            duracion = (datetime.now(utc_4) - inicio).total_seconds()
            logger.info(
                f"[yapo] Scrape finalizado — {len(avisos_validos)} avisos válidos"
                f" listos para carga ({duracion:.1f}s)"
            )

            # ── Reporte de ejecución → S3 (siempre, con o sin fallos) ────────
            if self.guardar_raw and carpeta:
                ruta_reporte = carpeta / "processed" / "run_report.json"
                reporte = {
                    "fuente": "yapo",
                    "timestamp": inicio.isoformat(),
                    "duracion_segundos": round(duracion, 1),
                    "avisos_encontrados": len(avisos_raw),
                    "avisos_unicos": len(vistos_dedup_id),
                    "avisos_validos": len(avisos_validos),
                    "avisos_rechazados": rechazados_total,
                    "fail_logs": [asdict(fl) for fl in fail_logs],
                }
                try:
                    ruta_reporte.write_text(
                        json.dumps(reporte, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                    log_meta.info(
                        f"[yapo] Reporte escrito — {len(fail_logs)} FAIL LOGs, {duracion:.1f}s"
                    )
                    await cargar_a_s3_con_retry(
                        ruta_reporte,
                        f"yapo/{fecha_dia}/logs/run_report.json",
                        etiqueta_log="yapo",
                    )
                except Exception as e:
                    log_meta.error(f"[yapo] No se pudo escribir run_report.json: {e}")
            elif fail_logs:
                logger.info(
                    f"[yapo] {len(fail_logs)} FAIL LOGs generados (guardar_raw=False, no persistidos)"
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
        scraper = ScraperYapoCloud(max_paginas=max_paginas, guardar_raw=True)
        async with AsyncSessionLocal() as sesion:
            resultado = await scraper.ejecutar(sesion)
        logger.info(
            f"[yapo] ejecutar() finalizado — {len(resultado.avisos)} avisos,"
            f" {resultado.errores} errores"
        )

    asyncio.run(_main())
