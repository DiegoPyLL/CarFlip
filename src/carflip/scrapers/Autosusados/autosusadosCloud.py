"""
Pipeline cloud completo para AutosUsados Chile.

El sitio es Next.js: cada página de listado embebe los avisos como JSON
estructurado en <script id="__NEXT_DATA__"> (props.pageProps.initialPosts),
por lo que no se parsea HTML de cards — se lee el JSON directamente.

Etapas cubiertas en scrape():
  1. INGESTA      — paginación ?page=N, parseo del JSON embebido, descarga de fotos
  2. LIMPIEZA     — deduplicación por id_externo
  3. VALIDACIÓN   — validación estructural y semántica; avisos inválidos van a FAIL LOG
  4. CARGA        — delegada a ScraperBase.ejecutar() vía uploader.upsert_avisos()

El sitio aplica rate limiting (HTTP 429 embebido en el JSON como
initialPosts={"error": {...}}): los reintentos usan backoff largo.
"""

import asyncio
import json
import math
import random
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from urllib.parse import quote

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parents[4]))

import httpx
from fake_useragent import UserAgent
from loguru import logger

from carflip.config import settings
from carflip.database.models import AutosusadosListing
from carflip.scrapers.base import AvisoAuto, ScraperBase, construir_id_externo
from carflip.scrapers.image_utils import convertir_a_avif
from carflip.storage.r2 import subir_objeto_con_retry, url_publica

CODIGO_FUENTE = 103  # identificador único de autosusados (ver ScraperBase.codigo_fuente)

BASE_URL = "https://autosusados.cl"
URL_LISTADO = f"{BASE_URL}/autos-usados"

_PATRON_NEXT_DATA = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.DOTALL
)
_PATRON_FECHA = re.compile(r"^\d{4}-\d{2}-\d{2}$")

_AÑO_MINIMO = 1970
_PRECIO_MINIMO = 500_000
_PRECIO_MAXIMO = 250_000_000

_AVISOS_POR_PAGINA = 20  # tamaño de página fijo del sitio

# El sitio pagina con ?page=N. Un `?pagina=N` (nombre viejo) es ignorado por el
# servidor y devuelve siempre la página 1 — silenciosamente, sin error.
_PARAM_PAGINA = "page"

_MAX_REINTENTOS_GET = 10   # reintentos por página antes de saltar a la siguiente
_BACKOFF_RATE_LIMIT = 20.0  # segundos de espera al recibir un error de rate limit

_CONCURRENCIA_PAGINAS = 3   # páginas procesadas en paralelo por lote
_SEM_IMGS = 20              # descargas de imagen concurrentes

# Tope de seguridad absoluto: el catálogo real ronda ~97 páginas (~1.940 avisos).
# Protege contra el bug de paginación descrito arriba (rate limit transitorio
# tras el fin del catálogo enmascarando la señal de fin) y cualquier otra causa
# de paginación descontrolada, sin depender de `paginas_sitio` ni de `max_paginas`.
_MAX_PAGINAS_ABSOLUTO = 120

# categoryID → segmento de categoría en la URL de detalle
# (/{categoria}/{MARCA}/{MODELO}/{table}/{carID}); mapeo verificado contra
# los sitemaps oficiales del sitio.
_CATEGORIAS = {1: "autos", 2: "camionetas", 3: "suv"}
_CATEGORIA_DEFAULT = "autos"

# Números oficiales de regiones de Chile — el JSON entrega `region` numérica.
_REGIONES = {
    1: "Tarapacá",
    2: "Antofagasta",
    3: "Atacama",
    4: "Coquimbo",
    5: "Valparaíso",
    6: "O'Higgins",
    7: "Maule",
    8: "Biobío",
    9: "La Araucanía",
    10: "Los Lagos",
    11: "Aysén",
    12: "Magallanes",
    13: "Metropolitana",
    14: "Los Ríos",
    15: "Arica y Parinacota",
    16: "Ñuble",
}


# ─── FAIL LOG ────────────────────────────────────────────────────────────────


@dataclass
class FailLog:
    etapa: str
    motivo: str
    id_externo: str
    fuente: str = "autosusados"
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
        _log.debug(f"[autosusados] {len(avisos)} avisos appended a {ruta_jsonl.name}")
        return True
    except Exception as e:
        _log.error(f"[autosusados] Error appending avisos a JSONL: {e}")
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
        _log.debug(f"[autosusados] Imagen ya existe: {ruta_orig.name}")
        ruta_avif = carpeta_fotos_processed / f"{aviso.id_externo}.avif"
        return ruta_orig, ruta_avif if ruta_avif.exists() else None
    async with semaforo_imgs:
        try:
            resp = await cliente.get(aviso.url_imagen, headers={"User-Agent": ua.random}, timeout=20.0)
            resp.raise_for_status()
            ruta_orig.write_bytes(resp.content)
        except Exception as e:
            _log.warning(f"[autosusados] No se pudo descargar imagen id={aviso.id_externo}: {e}")
            return None, None
    # Conversión AVIF en thread pool — es CPU-bound, no debe bloquear el event loop
    ruta_avif = await asyncio.to_thread(convertir_a_avif, ruta_orig, destino=carpeta_fotos_processed)
    if ruta_avif is None:
        fail_logs.append(FailLog(
            etapa="conversion_avif",
            motivo="Conversión AVIF fallida",
            id_externo=aviso.id_externo,
        ))
        _log.debug(f"[autosusados] Imagen descargada (sin AVIF): id={aviso.id_externo} → {ruta_orig.name}")
    else:
        _log.debug(
            f"[autosusados] Imagen descargada y convertida:"
            f" id={aviso.id_externo} → raw/{ruta_orig.name}, processed/{ruta_avif.name}"
        )
    return ruta_orig, ruta_avif


# ─── PARSEO DEL JSON EMBEBIDO ────────────────────────────────────────────────


def _extraer_posts(html: str) -> list[dict] | dict | None:
    """Extrae initialPosts del <script id="__NEXT_DATA__"> de una página de listado.

    Retorna la lista de posts, un dict {"error": ...} si el sitio respondió con
    rate limit, o None si el HTML no trae el JSON esperado.
    """
    match = _PATRON_NEXT_DATA.search(html)
    if not match:
        return None
    try:
        data = json.loads(match.group(1))
        return data["props"]["pageProps"]["initialPosts"]
    except (json.JSONDecodeError, KeyError, TypeError):
        return None


def _url_detalle(post: dict) -> str:
    """Construye la URL de detalle /{categoria}/{MARCA}/{MODELO}/{table}/{carID}."""
    categoria = _CATEGORIAS.get(post.get("categoryID"), _CATEGORIA_DEFAULT)
    marca = quote(str(post.get("brandName", "")), safe="")
    modelo = quote(str(post.get("modelName", "")), safe="")
    return f"{BASE_URL}/{categoria}/{marca}/{modelo}/{post.get('table', 1)}/{post.get('carID')}"


def _parsear_post(post: dict) -> AvisoAuto | None:
    """Mapea un post del JSON de listado a AvisoAuto."""
    car_id = post.get("carID")
    if not car_id:
        return None

    url = _url_detalle(post)
    id_externo = construir_id_externo(url)

    marca_raw = str(post.get("brandName") or "").strip()
    modelo_raw = str(post.get("modelName") or "").strip()
    marca = marca_raw.title() or None
    modelo = modelo_raw.title() or None

    descripcion = str(post.get("description") or "").strip() or None
    titulo = descripcion or f"{marca or ''} {modelo or ''} {post.get('year') or ''}".strip()

    precio_raw = post.get("price")
    precio = Decimal(precio_raw) if isinstance(precio_raw, (int, float)) and precio_raw > 0 else None

    km = post.get("kilometers") if isinstance(post.get("kilometers"), int) else None
    anio = post.get("year") if isinstance(post.get("year"), int) else None
    combustible = str(post.get("fuelName") or "").strip() or None
    ubicacion = _REGIONES.get(post.get("region"))
    url_imagen = str(post.get("photo") or "").strip() or None

    # Advertencias de ingesta por campos recuperables faltantes
    _log_i = logger.bind(fase="ingesta")
    if precio is None:
        _log_i.warning(f"[autosusados] id={id_externo} sin precio (carID={car_id})")
    if km is None:
        _log_i.warning(f"[autosusados] id={id_externo} km no encontrado (carID={car_id})")

    return AvisoAuto(
        fuente="autosusados",
        id_externo=id_externo,
        url=url,
        titulo=titulo,
        precio=precio,
        moneda="CLP",
        marca=marca,
        modelo=modelo,
        anio=anio,
        km=km,
        ubicacion=ubicacion,
        combustible=combustible,
        descripcion=descripcion,
        url_imagen=url_imagen,
        disponible=True,
    )


# ─── SCRAPER CLOUD ────────────────────────────────────────────────────────────


class ScraperAutosusadosCloud(ScraperBase):
    """
    Scraper de AutosUsados con pipeline cloud completo:
    ingesta → limpieza → validación → retorno para carga.
    """

    fuente = "autosusados"
    codigo_fuente = CODIGO_FUENTE
    model_class = AutosusadosListing

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

        carpeta_logs = carpeta_logs_run("autosusados", inicio.replace(tzinfo=None))
        sink_ids = configurar_sinks_run("autosusados", carpeta_logs)

        log_ingesta   = logger.bind(fase="ingesta")
        log_fotos     = logger.bind(fase="ingesta", tipo="fotos")
        log_meta      = logger.bind(fase="ingesta", tipo="metadata")
        log_limpieza  = logger.bind(fase="limpieza")
        log_validacion = logger.bind(fase="validacion")

        logger.info(f"[autosusados] Iniciando scrape cloud — {inicio.strftime('%H:%M:%S %d/%m/%Y')}")

        fail_logs: list[FailLog] = []
        avisos_raw: list[AvisoAuto] = []
        vistos_car_id: set[int] = set()
        paginas_procesadas = 0
        fotos_ok_total = 0
        fotos_total = 0
        paginas_sitio: int | None = None  # calculado desde el campo `total` del JSON

        fecha_str = inicio.strftime("%H-%M-%S_%d-%m-%Y")
        carpeta = _carpeta_run(Path("autosusados"), fecha_str) if self.guardar_raw else None
        ruta_jsonl = carpeta / "raw" / "avisos.jsonl" if carpeta else None
        carpeta_fotos_raw = carpeta / "raw" / "fotos" if carpeta else None
        carpeta_fotos_processed = carpeta / "processed" / "fotos" if carpeta else None

        lock_vistos = asyncio.Lock()
        lock_jsonl = asyncio.Lock()
        sem_imgs = asyncio.Semaphore(_SEM_IMGS)
        fin_paginacion = asyncio.Event()

        try:
            # ── INGESTA ──────────────────────────────────────────────────────
            log_banner_fase("autosusados", 1, "INGESTA")
            t_ingesta = datetime.now()
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as cliente:

                async def _obtener_posts(pagina: int) -> tuple[list[dict] | None, bool]:
                    """GET de una página de listado con reintentos y backoff ante rate limit.

                    Retorna (posts, tuvo_rate_limit). tuvo_rate_limit es True si algún
                    intento fue rechazado por rate limiting, incluso si finalmente se
                    obtuvo una respuesta válida — la llamante lo usa para no confiar en
                    un "sin avisos nuevos" que puede ser una respuesta obsoleta.
                    """
                    tuvo_rate_limit = False
                    for intento in range(1, _MAX_REINTENTOS_GET + 1):
                        log_ingesta.debug(
                            f"[autosusados] GET {URL_LISTADO} params={{{_PARAM_PAGINA}: {pagina}}}"
                            + (f" — intento {intento}/{_MAX_REINTENTOS_GET}" if intento > 1 else "")
                        )
                        try:
                            headers = {"User-Agent": self._ua.random}
                            response = await cliente.get(
                                URL_LISTADO, params={_PARAM_PAGINA: pagina}, headers=headers
                            )
                            response.raise_for_status()
                            posts = _extraer_posts(response.text)
                            if isinstance(posts, list):
                                return posts, tuvo_rate_limit
                            # El sitio embebe el error de rate limit en el JSON
                            motivo = posts.get("error") if isinstance(posts, dict) else "sin __NEXT_DATA__"
                            raise RuntimeError(f"respuesta sin posts: {motivo}")
                        except Exception as e:
                            es_rate_limit = "429" in str(e) or "límite" in str(e).lower()
                            if es_rate_limit:
                                tuvo_rate_limit = True
                            espera = _BACKOFF_RATE_LIMIT + random.uniform(0, 5) if es_rate_limit else 2.0
                            if intento < _MAX_REINTENTOS_GET:
                                log_ingesta.warning(
                                    f"[autosusados] Error en página {pagina}"
                                    f" intento {intento}/{_MAX_REINTENTOS_GET}: {e}"
                                    f" — reintentando en {espera:.1f}s"
                                )
                                await asyncio.sleep(espera)
                            else:
                                log_ingesta.error(
                                    f"[autosusados] Página {pagina}: agotados {_MAX_REINTENTOS_GET}"
                                    f" reintentos, continuando con siguiente página"
                                )
                    return None, tuvo_rate_limit

                async def _tarea_pagina(pagina: int) -> tuple[list[AvisoAuto], int, int]:
                    """Procesa una página completa. Retorna (avisos, imgs_ok, imgs_total)."""
                    nonlocal paginas_sitio
                    if fin_paginacion.is_set():
                        return [], 0, 0

                    posts, tuvo_rate_limit = await _obtener_posts(pagina)
                    if posts is None:
                        return [], 0, 0

                    if paginas_sitio is None and posts and isinstance(posts[0].get("total"), int):
                        paginas_sitio = math.ceil(posts[0]["total"] / _AVISOS_POR_PAGINA)
                        log_ingesta.info(
                            f"[autosusados] Sitio reporta {posts[0]['total']} avisos"
                            f" (~{paginas_sitio} páginas)"
                        )

                    nuevos: list[dict] = []
                    async with lock_vistos:
                        for post in posts:
                            car_id = post.get("carID")
                            if car_id and car_id not in vistos_car_id:
                                vistos_car_id.add(car_id)
                                nuevos.append(post)

                    # El sitio puede devolver posts no vacíos pero todos ya vistos.
                    # Si ocurrió durante/tras un rate limit, es probable una respuesta
                    # cacheada/obsoleta — se omite sin cortar paginación. Si se obtuvo
                    # limpiamente sin rate limit, entonces es señal genuina de fin.
                    # Una lista `posts` VACÍA es distinta: el servidor no devolvió
                    # avisos porque no hay más catálogo, señal inequívoca de fin
                    # aunque haya habido rate limit en algún reintento previo de esta
                    # misma página. Tratarla como "posible respuesta obsoleta" (rama
                    # de abajo) hacía que la paginación nunca cortara ante 429s
                    # transitorios pasado el fin real del catálogo — el scraper
                    # seguía pidiendo páginas indefinidamente (se observó llegar a
                    # la página 130 con un catálogo real de ~97 páginas).
                    if not nuevos:
                        if tuvo_rate_limit and posts:
                            log_ingesta.warning(
                                f"[autosusados] Página {pagina}: sin avisos nuevos tras rate limit"
                                f" — probable respuesta obsoleta, se omite sin cortar paginación"
                            )
                            fail_logs.append(FailLog(
                                etapa="rate_limit_paginacion",
                                motivo="Página retornó solo duplicados tras backoff de rate limit; se omite",
                                id_externo=f"pagina_{pagina}",
                            ))
                            return [], 0, 0
                        log_ingesta.info(
                            f"[autosusados] Página {pagina}: sin avisos nuevos, fin paginación"
                        )
                        fin_paginacion.set()
                        return [], 0, 0

                    avisos_pagina: list[AvisoAuto] = []
                    for post in nuevos:
                        try:
                            aviso = _parsear_post(post)
                            if aviso:
                                log_ingesta.debug(f"[autosusados] Parseando aviso id={aviso.id_externo}")
                                avisos_pagina.append(aviso)
                        except Exception as e:
                            log_ingesta.warning(f"[autosusados] Error parseando post en página {pagina}: {e}")

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
                                else:
                                    fail_logs.append(FailLog(
                                        etapa="descarga_foto",
                                        motivo="Descarga de imagen fallida",
                                        id_externo=aviso.id_externo,
                                    ))
                                if ruta_avif is not None:
                                    # Clave estable por aviso: re-scrapearlo no vuelve a subir la foto.
                                    clave_proc = f"fotos/autosusados/{aviso.id_externo}.avif"
                                    tareas_s3_info.append(
                                        (
                                            subir_objeto_con_retry(
                                                ruta_avif, clave_proc, etiqueta_log="autosusados",
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
                                f"[autosusados] Página {pagina}: {imgs_ok_pag}/{imgs_total_pag} imágenes descargadas"
                                + (f" ({imgs_fail} fallida{'s' if imgs_fail > 1 else ''})" if imgs_fail else "")
                            )
                            if tareas_s3_info:
                                resultados_s3 = await asyncio.gather(*[t[0] for t in tareas_s3_info])
                                for (_, aviso, etapa, clave), s3_ok in zip(tareas_s3_info, resultados_s3):
                                    if not s3_ok:
                                        fail_logs.append(FailLog(
                                            etapa=etapa,
                                            motivo="R2 upload agotó reintentos",
                                            id_externo=aviso.id_externo,
                                        ))
                                    elif etapa == "upload_foto_processed":
                                        if url_cdn := url_publica(clave):
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
                                f"[autosusados] Página {pagina}: {len(avisos_pagina)} avisos guardados en JSONL"
                            )

                    log_ingesta.debug(f"[autosusados] Página {pagina}: {len(avisos_pagina)} avisos obtenidos")
                    return avisos_pagina, imgs_ok_pag, imgs_total_pag

                # ── Tarea con stagger — evita ráfaga simultánea de requests del mismo lote ──
                async def _tarea_con_stagger(p: int, idx: int) -> tuple[list[AvisoAuto], int, int]:
                    if idx > 0:
                        await asyncio.sleep(idx * random.uniform(0.8, 2.0))
                    return await _tarea_pagina(p)

                # ── Procesamiento por lotes: _CONCURRENCIA_PAGINAS páginas en paralelo ──
                pagina = 1
                while not fin_paginacion.is_set() and (self.max_paginas is None or pagina <= self.max_paginas):
                    if pagina > _MAX_PAGINAS_ABSOLUTO:
                        log_ingesta.warning(
                            f"[autosusados] Alcanzado el tope de seguridad de"
                            f" {_MAX_PAGINAS_ABSOLUTO} páginas, fin paginación"
                        )
                        break
                    if paginas_sitio is not None and pagina > paginas_sitio:
                        log_ingesta.info(
                            f"[autosusados] Página {pagina} supera las ~{paginas_sitio} del sitio, fin"
                        )
                        break
                    fin_lote = pagina + _CONCURRENCIA_PAGINAS
                    fin_lote = min(fin_lote, _MAX_PAGINAS_ABSOLUTO + 1)
                    if self.max_paginas is not None:
                        fin_lote = min(fin_lote, self.max_paginas + 1)
                    if paginas_sitio is not None:
                        fin_lote = min(fin_lote, paginas_sitio + 1)
                    nums_lote = list(range(pagina, fin_lote))

                    resultados_lote = await asyncio.gather(
                        *[_tarea_con_stagger(p, i) for i, p in enumerate(nums_lote)],
                        return_exceptions=True,
                    )

                    for resultado in resultados_lote:
                        if isinstance(resultado, BaseException):
                            log_ingesta.error(f"[autosusados] Error inesperado en tarea de página: {resultado}")
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
            log_resumen_fase("autosusados", "INGESTA", {
                "avisos": len(avisos_raw),
                "páginas": paginas_procesadas,
                "fotos": f"{fotos_ok_total}/{fotos_total}" if fotos_total else "n/a",
                "duración": f"{duracion_ingesta:.0f}s",
            })

            # ── LIMPIEZA (deduplicación por id_externo) ───────────────────────
            log_banner_fase("autosusados", 2, "LIMPIEZA")
            vistos_id: set[str] = set()
            avisos_unicos: list[AvisoAuto] = []
            for aviso in avisos_raw:
                if aviso.id_externo in vistos_id:
                    log_limpieza.warning(f"[autosusados] Duplicado detectado id={aviso.id_externo}, descartando")
                    fail_logs.append(FailLog(
                        etapa="dedup_json",
                        motivo="id_externo duplicado entre páginas",
                        id_externo=aviso.id_externo,
                    ))
                else:
                    vistos_id.add(aviso.id_externo)
                    avisos_unicos.append(aviso)

            dups = len(avisos_raw) - len(avisos_unicos)
            log_resumen_fase("autosusados", "LIMPIEZA", {
                "entrada": len(avisos_raw),
                "únicos": len(avisos_unicos),
                "duplicados": dups,
            })

            # ── VALIDACIÓN ────────────────────────────────────────────────────
            log_banner_fase("autosusados", 3, "VALIDACIÓN")
            avisos_validos: list[AvisoAuto] = []
            rechazados = 0
            for aviso in avisos_unicos:
                errores = _validar_aviso(aviso)
                if errores:
                    log_validacion.error(f"[autosusados] Aviso rechazado id={aviso.id_externo}: {errores}")
                    fail_logs.append(FailLog(
                        etapa="validacion_json",
                        motivo="; ".join(errores),
                        id_externo=aviso.id_externo,
                    ))
                    rechazados += 1
                else:
                    avisos_validos.append(aviso)

            log_resumen_fase("autosusados", "VALIDACIÓN", {
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
                        f"[autosusados] {len(avisos_validos)} avisos procesados escritos en {ruta_procesados}"
                    )
                else:
                    log_meta.error(f"[autosusados] Error al escribir avisos procesados en {ruta_procesados}")

            duracion = (datetime.now(utc_4) - inicio).total_seconds()
            logger.info(
                f"[autosusados] Scrape finalizado — {len(avisos_validos)} avisos válidos"
                f" listos para carga ({duracion:.1f}s)"
            )

            # ── Reporte de ejecución (siempre, con o sin fallos) ─────────────
            # ejecutar() lo persiste en scrape_runs; la copia local queda para depurar.
            self.ultimo_reporte = {
                "fuente": "autosusados",
                "timestamp": inicio.isoformat(),
                "duracion_segundos": round(duracion, 1),
                "paginas_procesadas": paginas_procesadas,
                "avisos_encontrados": len(avisos_raw),
                "avisos_unicos": len(avisos_unicos),
                "avisos_validos": len(avisos_validos),
                "avisos_rechazados": len(avisos_unicos) - len(avisos_validos),
                "fail_logs": [asdict(fl) for fl in fail_logs],
            }
            log_meta.info(
                f"[autosusados] Reporte generado — {len(fail_logs)} FAIL LOGs, {duracion:.1f}s"
            )
            if self.guardar_raw and carpeta:
                ruta_reporte = carpeta / "processed" / "run_report.json"
                try:
                    ruta_reporte.write_text(
                        json.dumps(self.ultimo_reporte, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                except Exception as e:
                    log_meta.error(f"[autosusados] No se pudo escribir run_report.json: {e}")

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
        scraper = ScraperAutosusadosCloud(max_paginas=max_paginas, guardar_raw=True)
        async with AsyncSessionLocal() as sesion:
            resultado = await scraper.ejecutar(sesion)
        logger.info(
            f"[autosusados] ejecutar() finalizado — {len(resultado.avisos)} avisos,"
            f" {resultado.errores} errores"
        )

    asyncio.run(_main())
