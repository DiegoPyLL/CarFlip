"""
Pipeline cloud completo para Checkeados Chile.

El listado /comprar es un export estático de Next.js (HTML idéntico sin
importar query params) que carga el catálogo client-side contra
GET /api/vehicles?status=...&limit=20&offset=N — confirmado inspeccionando
las llamadas de red reales del sitio público (sin cookies ni login). El
sitemap oficial y las páginas por marca existen pero ambos topan en 20
resultados, muy por debajo del inventario real (~125 avisos); por eso el
scraper pagina directamente ese endpoint, que es el mismo que usa cualquier
visitante anónimo de /comprar. Cada item ya viene con los mismos campos que
antes se leían del <script id="__NEXT_DATA__"> de la página de detalle, así
que no hace falta visitar cada aviso individualmente.

Etapas cubiertas en scrape():
  1. INGESTA      — paginación de /api/vehicles por offset, descarga de fotos
  2. LIMPIEZA     — deduplicación por id_externo
  3. VALIDACIÓN   — validación estructural y semántica; avisos inválidos van a FAIL LOG
  4. CARGA        — delegada a ScraperBase.ejecutar() vía uploader.upsert_avisos()
"""

import asyncio
import json
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
from carflip.database.models import CheckeadosListing
from carflip.scrapers.base import AvisoAuto, ScraperBase, construir_id_externo
from carflip.scrapers.image_utils import convertir_a_avif
from carflip.storage.r2 import subir_objeto_con_retry, url_publica

CODIGO_FUENTE = 104  # identificador único de checkeados (ver ScraperBase.codigo_fuente)

BASE_URL = "https://www.checkeados.cl"
URL_API_VEHICULOS = f"{BASE_URL}/api/vehicles"
URL_API_CONTEO = f"{BASE_URL}/api/vehicles/count"

# Mismos estados que el frontend público de /comprar pide para su listado
# (capturado inspeccionando las llamadas de red reales de la página; excluye
# "Comprado/Consignado - No publicado", que el sitio no muestra como inventario).
_ESTADOS_INVENTARIO = (
    "Publicado,Comprado - En preparación,Consignado - En preparación,"
    "En preparación - Listo,Control de Calidad - Aprobado"
)

_PATRON_FECHA = re.compile(r"^\d{4}-\d{2}-\d{2}$")

_AÑO_MINIMO = 1970
_PRECIO_MINIMO = 500_000
_PRECIO_MAXIMO = 250_000_000

_MAX_REINTENTOS_GET = 10  # reintentos por request antes de saltar a la siguiente página

_LIMIT_PAGINA = 20          # tope máximo que acepta el endpoint (valores mayores se ignoran)
_CONCURRENCIA_PAGINAS = 3   # páginas procesadas en paralelo por lote
_SEM_IMGS = 20              # descargas de imagen concurrentes


# ─── FAIL LOG ────────────────────────────────────────────────────────────────


@dataclass
class FailLog:
    etapa: str
    motivo: str
    id_externo: str
    fuente: str = "checkeados"
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
        _log.debug(f"[checkeados] {len(avisos)} avisos appended a {ruta_jsonl.name}")
        return True
    except Exception as e:
        _log.error(f"[checkeados] Error appending avisos a JSONL: {e}")
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
    ext = Path(aviso.url_imagen.split("?")[0]).suffix or ".png"
    ruta_orig = carpeta_fotos_raw / f"{aviso.id_externo}{ext}"
    if ruta_orig.exists():
        _log.debug(f"[checkeados] Imagen ya existe: {ruta_orig.name}")
        ruta_avif = carpeta_fotos_processed / f"{aviso.id_externo}.avif"
        return ruta_orig, ruta_avif if ruta_avif.exists() else None
    async with semaforo_imgs:
        try:
            resp = await cliente.get(aviso.url_imagen, headers={"User-Agent": ua.random}, timeout=20.0)
            resp.raise_for_status()
            ruta_orig.write_bytes(resp.content)
        except Exception as e:
            _log.warning(f"[checkeados] No se pudo descargar imagen id={aviso.id_externo}: {e}")
            return None, None
    # Conversión AVIF en thread pool — es CPU-bound, no debe bloquear el event loop
    ruta_avif = await asyncio.to_thread(convertir_a_avif, ruta_orig, destino=carpeta_fotos_processed)
    if ruta_avif is None:
        fail_logs.append(FailLog(
            etapa="conversion_avif",
            motivo="Conversión AVIF fallida",
            id_externo=aviso.id_externo,
        ))
        _log.debug(f"[checkeados] Imagen descargada (sin AVIF): id={aviso.id_externo} → {ruta_orig.name}")
    else:
        _log.debug(
            f"[checkeados] Imagen descargada y convertida:"
            f" id={aviso.id_externo} → raw/{ruta_orig.name}, processed/{ruta_avif.name}"
        )
    return ruta_orig, ruta_avif


# ─── PARSEO ──────────────────────────────────────────────────────────────────


def _url_detalle(vehicle: dict) -> str:
    """Construye la URL pública /comprar/{marca}~{modelo}~{año}~{id[:4]}.

    Patrón confirmado comparando los href reales del listado con el id de
    cada vehículo: el último segmento son los primeros 4 caracteres del id.
    """
    marca = quote(str(vehicle.get("brand") or "").lower(), safe="")
    modelo = quote(str(vehicle.get("model") or "").lower(), safe="")
    anio = vehicle.get("year") or ""
    codigo = str(vehicle.get("id") or "")[:4]
    return f"{BASE_URL}/comprar/{marca}~{modelo}~{anio}~{codigo}"


def _parsear_vehicle(vehicle: dict, url: str) -> AvisoAuto | None:
    """Mapea el JSON vehicle de una página de detalle a AvisoAuto."""
    if not vehicle.get("id"):
        return None

    id_externo = construir_id_externo(url)

    marca_raw = str(vehicle.get("brand") or "").strip()
    modelo_raw = str(vehicle.get("model") or "").strip()
    marca = marca_raw.title() or None
    modelo = modelo_raw.title() or None
    version = str(vehicle.get("version") or "").strip()
    anio = vehicle.get("year") if isinstance(vehicle.get("year"), int) else None

    titulo = " ".join(p for p in [marca, modelo, version, str(anio or "")] if p).strip()

    precio_raw = vehicle.get("price")
    precio = Decimal(precio_raw) if isinstance(precio_raw, (int, float)) and precio_raw > 0 else None

    km = vehicle.get("kms") if isinstance(vehicle.get("kms"), int) else None
    combustible = str(vehicle.get("fuel") or "").strip() or None
    descripcion = str(vehicle.get("description") or "").strip() or None

    branch = vehicle.get("branch")
    ubicacion = None
    if isinstance(branch, dict):
        ubicacion = str(branch.get("name") or "").strip() or None

    url_imagen = str(vehicle.get("mainImageUrl") or "").strip() or None
    if not url_imagen:
        imagenes = vehicle.get("images")
        if isinstance(imagenes, list) and imagenes and isinstance(imagenes[0], dict):
            url_imagen = str(imagenes[0].get("url") or "").strip() or None

    fecha_publicacion: str | None = None
    fecha_raw = str(vehicle.get("publicationDate") or "")
    if len(fecha_raw) >= 10:
        fecha_publicacion = fecha_raw[:10]

    disponible = vehicle.get("status") == "Publicado"

    # Advertencias de ingesta por campos recuperables faltantes
    _log_i = logger.bind(fase="ingesta")
    if precio is None:
        _log_i.warning(f"[checkeados] id={id_externo} sin precio")
    if km is None:
        _log_i.warning(f"[checkeados] id={id_externo} km no encontrado")

    return AvisoAuto(
        fuente="checkeados",
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
        disponible=disponible,
        fecha_publicacion=fecha_publicacion,
    )


# ─── SCRAPER CLOUD ────────────────────────────────────────────────────────────


class ScraperCheckeadosCloud(ScraperBase):
    """
    Scraper de Checkeados con pipeline cloud completo:
    ingesta → limpieza → validación → retorno para carga.

    `max_paginas` limita la cantidad de avisos procesados (no páginas de la API).
    """

    fuente = "checkeados"
    codigo_fuente = CODIGO_FUENTE
    model_class = CheckeadosListing

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

        carpeta_logs = carpeta_logs_run("checkeados", inicio.replace(tzinfo=None))
        sink_ids = configurar_sinks_run("checkeados", carpeta_logs)

        log_ingesta   = logger.bind(fase="ingesta")
        log_fotos     = logger.bind(fase="ingesta", tipo="fotos")
        log_meta      = logger.bind(fase="ingesta", tipo="metadata")
        log_limpieza  = logger.bind(fase="limpieza")
        log_validacion = logger.bind(fase="validacion")

        logger.info(f"[checkeados] Iniciando scrape cloud — {inicio.strftime('%H:%M:%S %d/%m/%Y')}")

        fail_logs: list[FailLog] = []
        avisos_raw: list[AvisoAuto] = []
        fotos_ok_total = 0
        fotos_total = 0

        fecha_str = inicio.strftime("%H-%M-%S_%d-%m-%Y")
        carpeta = _carpeta_run(Path("checkeados"), fecha_str) if self.guardar_raw else None
        ruta_jsonl = carpeta / "raw" / "avisos.jsonl" if carpeta else None
        carpeta_fotos_raw = carpeta / "raw" / "fotos" if carpeta else None
        carpeta_fotos_processed = carpeta / "processed" / "fotos" if carpeta else None

        lock_jsonl = asyncio.Lock()
        sem_imgs = asyncio.Semaphore(_SEM_IMGS)
        paginas_procesadas = 0

        try:
            # ── INGESTA ──────────────────────────────────────────────────────
            log_banner_fase("checkeados", 1, "INGESTA")
            t_ingesta = datetime.now()
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as cliente:

                # 1. Total de avisos en inventario público (define cuántas páginas pedir)
                total = 0
                for intento in range(1, _MAX_REINTENTOS_GET + 1):
                    try:
                        resp = await cliente.get(
                            URL_API_CONTEO,
                            params={"status": _ESTADOS_INVENTARIO},
                            headers={"User-Agent": self._ua.random},
                        )
                        resp.raise_for_status()
                        total = int(resp.json())
                        break
                    except Exception as e:
                        if intento < _MAX_REINTENTOS_GET:
                            log_ingesta.warning(
                                f"[checkeados] Error obteniendo conteo de inventario"
                                f" intento {intento}/{_MAX_REINTENTOS_GET}: {e} — reintentando en 2s"
                            )
                            await asyncio.sleep(2)
                        else:
                            log_ingesta.error(
                                f"[checkeados] Conteo de inventario: agotados"
                                f" {_MAX_REINTENTOS_GET} reintentos, abortando ingesta"
                            )

                if self.max_paginas is not None:
                    total = min(total, self.max_paginas)

                log_ingesta.info(f"[checkeados] {total} avisos en inventario público (API)")

                # 2. Páginas de /api/vehicles por offset → AvisoAuto
                async def _tarea_pagina(offset: int) -> list[AvisoAuto]:
                    vehiculos: list | None = None
                    for intento in range(1, _MAX_REINTENTOS_GET + 1):
                        try:
                            resp_p = await cliente.get(
                                URL_API_VEHICULOS,
                                params={
                                    "status": _ESTADOS_INVENTARIO,
                                    "limit": _LIMIT_PAGINA,
                                    "offset": offset,
                                },
                                headers={"User-Agent": self._ua.random},
                                timeout=25.0,
                            )
                            resp_p.raise_for_status()
                            data = resp_p.json()
                            vehiculos = data if isinstance(data, list) else None
                            break
                        except Exception as e:
                            if intento < _MAX_REINTENTOS_GET:
                                log_ingesta.warning(
                                    f"[checkeados] Error en offset {offset}"
                                    f" intento {intento}/{_MAX_REINTENTOS_GET}: {e} — reintentando en 2s"
                                )
                                await asyncio.sleep(2)
                            else:
                                log_ingesta.error(
                                    f"[checkeados] Offset {offset}: agotados"
                                    f" {_MAX_REINTENTOS_GET} reintentos, saltando página"
                                )
                    if vehiculos is None:
                        fail_logs.append(FailLog(
                            etapa="ingesta_pagina",
                            motivo="GET de /api/vehicles agotó reintentos o respuesta inválida",
                            id_externo=f"offset={offset}",
                        ))
                        return []

                    avisos_pagina: list[AvisoAuto] = []
                    for vehicle in vehiculos:
                        if not isinstance(vehicle, dict) or not vehicle.get("id"):
                            continue
                        url_det = _url_detalle(vehicle)
                        aviso = _parsear_vehicle(vehicle, url_det)
                        if aviso:
                            log_ingesta.debug(f"[checkeados] Parseando aviso id={aviso.id_externo}")
                            avisos_pagina.append(aviso)
                    return avisos_pagina

                offsets = list(range(0, total, _LIMIT_PAGINA)) if total > 0 else []
                for i in range(0, len(offsets), _CONCURRENCIA_PAGINAS):
                    lote = offsets[i : i + _CONCURRENCIA_PAGINAS]
                    resultados_lote = await asyncio.gather(
                        *[_tarea_pagina(off) for off in lote],
                        return_exceptions=True,
                    )
                    for resultado in resultados_lote:
                        if isinstance(resultado, BaseException):
                            log_ingesta.error(f"[checkeados] Error inesperado en tarea de página: {resultado}")
                            continue
                        avisos_raw.extend(resultado)
                        paginas_procesadas += 1
                    if i + _CONCURRENCIA_PAGINAS < len(offsets):
                        await self.espera_aleatoria()

                # 3. Descargar fotos con concurrencia controlada por sem_imgs
                fotos_run: dict[str, str] = {}
                if self.guardar_raw and carpeta_fotos_raw and carpeta_fotos_processed and avisos_raw:
                    tareas_img = [
                        _descargar_imagen(
                            cliente, a, carpeta_fotos_raw, carpeta_fotos_processed,
                            self._ua, fail_logs, sem_imgs,
                        )
                        for a in avisos_raw
                        if a.url_imagen
                    ]
                    if tareas_img:
                        fotos_total = len(tareas_img)
                        resultados = await asyncio.gather(*tareas_img, return_exceptions=True)
                        avisos_con_imagen = [a for a in avisos_raw if a.url_imagen]
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
                                fotos_run[aviso.id_externo] = ruta_orig.name
                            else:
                                fail_logs.append(FailLog(
                                    etapa="descarga_foto",
                                    motivo="Descarga de imagen fallida",
                                    id_externo=aviso.id_externo,
                                ))
                            if ruta_avif is not None:
                                # Clave estable por aviso: re-scrapearlo no vuelve a subir la foto.
                                clave_proc = f"fotos/checkeados/{aviso.id_externo}.avif"
                                tareas_s3_info.append(
                                    (
                                        subir_objeto_con_retry(
                                            ruta_avif, clave_proc, etiqueta_log="checkeados",
                                            skip_si_existe=True,
                                        ),
                                        aviso,
                                        "upload_foto_processed",
                                        clave_proc,
                                    )
                                )
                        fotos_ok_total = sum(
                            1 for r in resultados if isinstance(r, tuple) and r[0] is not None
                        )
                        imgs_fail = fotos_total - fotos_ok_total
                        log_fotos.info(
                            f"[checkeados] {fotos_ok_total}/{fotos_total} imágenes descargadas"
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

                # 4. Append JSONL con lock para evitar escrituras concurrentes
                if self.guardar_raw and ruta_jsonl and avisos_raw:
                    async with lock_jsonl:
                        ok = _append_avisos_jsonl(avisos_raw, ruta_jsonl, fotos=fotos_run)
                    if not ok:
                        for aviso in avisos_raw:
                            fail_logs.append(FailLog(
                                etapa="dedup_json",
                                motivo="Error al serializar JSONL",
                                id_externo=aviso.id_externo,
                            ))
                    else:
                        log_meta.info(
                            f"[checkeados] {len(avisos_raw)} avisos guardados en JSONL"
                        )

            duracion_ingesta = (datetime.now() - t_ingesta).total_seconds()
            log_resumen_fase("checkeados", "INGESTA", {
                "avisos": len(avisos_raw),
                "páginas": paginas_procesadas,
                "fotos": f"{fotos_ok_total}/{fotos_total}" if fotos_total else "n/a",
                "duración": f"{duracion_ingesta:.0f}s",
            })

            # ── LIMPIEZA (deduplicación por id_externo) ───────────────────────
            log_banner_fase("checkeados", 2, "LIMPIEZA")
            vistos_id: set[str] = set()
            avisos_unicos: list[AvisoAuto] = []
            for aviso in avisos_raw:
                if aviso.id_externo in vistos_id:
                    log_limpieza.warning(f"[checkeados] Duplicado detectado id={aviso.id_externo}, descartando")
                    fail_logs.append(FailLog(
                        etapa="dedup_json",
                        motivo="id_externo duplicado entre páginas de /api/vehicles",
                        id_externo=aviso.id_externo,
                    ))
                else:
                    vistos_id.add(aviso.id_externo)
                    avisos_unicos.append(aviso)

            dups = len(avisos_raw) - len(avisos_unicos)
            log_resumen_fase("checkeados", "LIMPIEZA", {
                "entrada": len(avisos_raw),
                "únicos": len(avisos_unicos),
                "duplicados": dups,
            })

            # ── VALIDACIÓN ────────────────────────────────────────────────────
            log_banner_fase("checkeados", 3, "VALIDACIÓN")
            avisos_validos: list[AvisoAuto] = []
            rechazados = 0
            for aviso in avisos_unicos:
                errores = _validar_aviso(aviso)
                if errores:
                    log_validacion.error(f"[checkeados] Aviso rechazado id={aviso.id_externo}: {errores}")
                    fail_logs.append(FailLog(
                        etapa="validacion_json",
                        motivo="; ".join(errores),
                        id_externo=aviso.id_externo,
                    ))
                    rechazados += 1
                else:
                    avisos_validos.append(aviso)

            log_resumen_fase("checkeados", "VALIDACIÓN", {
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
                        f"[checkeados] {len(avisos_validos)} avisos procesados escritos en {ruta_procesados}"
                    )
                else:
                    log_meta.error(f"[checkeados] Error al escribir avisos procesados en {ruta_procesados}")

            duracion = (datetime.now(utc_4) - inicio).total_seconds()
            logger.info(
                f"[checkeados] Scrape finalizado — {len(avisos_validos)} avisos válidos"
                f" listos para carga ({duracion:.1f}s)"
            )

            # ── Reporte de ejecución (siempre, con o sin fallos) ─────────────
            # ejecutar() lo persiste en scrape_runs; la copia local queda para depurar.
            self.ultimo_reporte = {
                "fuente": "checkeados",
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
                f"[checkeados] Reporte generado — {len(fail_logs)} FAIL LOGs, {duracion:.1f}s"
            )
            if self.guardar_raw and carpeta:
                ruta_reporte = carpeta / "processed" / "run_report.json"
                try:
                    ruta_reporte.write_text(
                        json.dumps(self.ultimo_reporte, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                except Exception as e:
                    log_meta.error(f"[checkeados] No se pudo escribir run_report.json: {e}")

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
        scraper = ScraperCheckeadosCloud(max_paginas=max_paginas, guardar_raw=True)
        async with AsyncSessionLocal() as sesion:
            resultado = await scraper.ejecutar(sesion)
        logger.info(
            f"[checkeados] ejecutar() finalizado — {len(resultado.avisos)} avisos,"
            f" {resultado.errores} errores"
        )

    asyncio.run(_main())
