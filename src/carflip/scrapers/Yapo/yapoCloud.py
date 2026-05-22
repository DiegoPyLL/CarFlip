"""
Pipeline cloud completo para Yapo Chile.

Etapas cubiertas en scrape():
  1. INGESTA      — navegación Playwright, extracción JS, descarga de fotos, guardado JSON por aviso
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

from loguru import logger
from playwright.async_api import async_playwright

from carflip.config import settings
from carflip.database.models import YapoListing
from carflip.scrapers.base import AvisoAuto, ScraperBase
from carflip.scrapers.image_utils import convertir_a_avif

YAPO_BASE = "https://www.yapo.cl"
_AÑO_MINIMO = 1970
_PRECIO_MINIMO = 500_000
_PRECIO_MAXIMO = 250_000_000
_PATRON_FECHA = re.compile(r"^\d{4}-\d{2}-\d{2}$")

_S3_MAX_REINTENTOS = 12   # 12 × 10 min = 2 horas
_S3_INTERVALO_SEG  = 600  # 10 minutos
_MAX_AVISOS        = 1_000

_HEADERS_HTTP = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": YAPO_BASE,
}


# ─── FAIL LOG ────────────────────────────────────────────────────────────────


@dataclass
class FailLog:
    etapa: str
    motivo: str
    id_externo: str
    fuente: str = "yapo"
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ─── CARGA S3 ────────────────────────────────────────────────────────────────


async def _cargar_a_s3_con_retry(ruta_local: Path, clave_s3: str) -> bool:
    import aioboto3
    from botocore.exceptions import ClientError

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
                logger.debug(f"[yapo] S3 upload OK: {clave_s3}")
                return True
            except (ClientError, Exception) as exc:
                if intento < _S3_MAX_REINTENTOS:
                    logger.warning(
                        f"[yapo] S3 upload fallido intento {intento}/{_S3_MAX_REINTENTOS}"
                        f" — {clave_s3}: {exc}. Reintentando en {_S3_INTERVALO_SEG // 60} min."
                    )
                    await asyncio.sleep(_S3_INTERVALO_SEG)
                else:
                    logger.error(
                        f"[yapo] S3 upload agotó {_S3_MAX_REINTENTOS} reintentos: {clave_s3} — {exc}"
                    )
    return False


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
        logger.debug(f"[yapo] {len(avisos)} avisos appended a {ruta_jsonl.name}")
        return True
    except Exception as e:
        logger.error(f"[yapo] Error appending avisos a JSONL: {e}")
        return False


# ─── SCRAPER CLOUD ────────────────────────────────────────────────────────────


class ScraperYapoCloud(ScraperBase):
    fuente = "yapo"
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
        url: str,
        ruta_raw: Path,
        carpeta_processed: Path,
        fail_logs: list[FailLog],
        aviso_id: str,
    ) -> tuple[Path | None, Path | None]:
        """Descarga la imagen original a raw/fotos/ y la convierte a AVIF en processed/fotos/."""
        if not url:
            return None, None
        if ruta_raw.exists():
            ruta_avif = carpeta_processed / f"{ruta_raw.stem}.avif"
            return ruta_raw, ruta_avif if ruta_avif.exists() else None
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, headers=_HEADERS_HTTP, timeout=15)
                resp.raise_for_status()
                ruta_raw.write_bytes(resp.content)
            ruta_avif = convertir_a_avif(ruta_raw, destino=carpeta_processed)
            if ruta_avif is None:
                fail_logs.append(FailLog(
                    etapa="conversion_avif",
                    motivo="Conversión AVIF fallida",
                    id_externo=aviso_id,
                ))
                logger.debug(f"[yapo] Imagen descargada (sin AVIF): id={aviso_id} → {ruta_raw.name}")
            else:
                logger.debug(
                    f"[yapo] Imagen descargada y convertida a AVIF:"
                    f" id={aviso_id} → raw/{ruta_raw.name}, processed/{ruta_avif.name}"
                )
            return ruta_raw, ruta_avif
        except Exception as e:
            logger.warning(f"[yapo] No se pudo descargar imagen {ruta_raw.name}: {e}")
            return None, None

    async def scrape(self) -> list[AvisoAuto]:
        utc_4 = timezone(timedelta(hours=-4))
        inicio = datetime.now(utc_4)
        fecha_str = inicio.strftime("%H-%M-%S_%d-%m-%Y")
        fecha_dia = inicio.strftime("%Y/%m/%d")
        carpeta = (Path("yapo") / fecha_str) if self.guardar_raw else None
        if carpeta:
            (carpeta / "raw" / "fotos").mkdir(parents=True, exist_ok=True)
            (carpeta / "processed" / "fotos").mkdir(parents=True, exist_ok=True)
        ruta_jsonl = carpeta / "raw" / "avisos.jsonl" if carpeta else None
        carpeta_fotos_raw = carpeta / "raw" / "fotos" if carpeta else None
        carpeta_fotos_processed = carpeta / "processed" / "fotos" if carpeta else None

        logger.info(f"[yapo] Iniciando scrape cloud — {inicio.strftime('%H:%M:%S %d/%m/%Y')}")

        fail_logs: list[FailLog] = []
        avisos_raw: list[AvisoAuto] = []
        fotos_run: dict[str, str] = {}
        vistos_urls: set[str] = set()
        avisos_info = []

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
            ctx = await browser.new_context(
                user_agent=_HEADERS_HTTP["User-Agent"],
                viewport={"width": 1280, "height": 800},
                locale="es-CL",
            )
            page = await ctx.new_page()
            await page.route("**/*.{png,jpg,jpeg,gif,webp,svg,woff,woff2,ttf,otf}", lambda route: route.abort())

            # ── INGESTA: listado ──────────────────────────────────────────────
            pagina = 0
            while True:
                pagina += 1
                if self.max_paginas and pagina > self.max_paginas:
                    break
                url = f"{YAPO_BASE}/autos-usados.{pagina}"
                logger.info(f"[yapo] Listado página {pagina}: {url}")
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                    await page.wait_for_selector("div.d3-ads-grid", timeout=20_000)
                except Exception as e:
                    logger.warning(f"[yapo] Timeout en página {pagina}: {e}")
                    break

                await page.wait_for_timeout(2_000)
                cards = await page.query_selector_all("div.d3-ad-tile")
                if not cards:
                    logger.info(f"[yapo] Página {pagina}: sin resultados, fin paginación")
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
                    if url_aviso in vistos_urls:
                        continue
                    vistos_urls.add(url_aviso)

                    async def _safe(sel: str) -> str:
                        try:
                            n = await card.query_selector(sel)
                            return (await n.inner_text()).strip() if n else ""
                        except Exception:
                            return ""

                    avisos_info.append({
                        "url": url_aviso,
                        "precio": await _safe("[class*='d3-ad-tile__price']"),
                        "region": await _safe("[class*='d3-ad-tile__location']"),
                        "fecha": await _safe("time, [class*='date']") or datetime.now().strftime("%Y-%m-%d"),
                    })

                nuevos = len(avisos_info) - count_antes
                logger.info(f"[yapo] Página {pagina}: {nuevos} URLs recolectadas (total {len(avisos_info)})")

                if len(avisos_info) >= _MAX_AVISOS:
                    avisos_info = avisos_info[:_MAX_AVISOS]
                    logger.info(f"[yapo] Límite de {_MAX_AVISOS} publicaciones alcanzado, deteniendo paginación")
                    break

            # ── INGESTA: detalles ─────────────────────────────────────────────
            for i, info in enumerate(avisos_info, 1):
                logger.debug(f"[yapo] Detalle {i}/{len(avisos_info)}: {info['url']}")
                url = info["url"]
                aviso_id = url.rstrip("/").split("/")[-1]

                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=25_000)
                    await page.wait_for_timeout(1_500)
                    attrs = await page.evaluate(self._JS_ATTRS)
                except Exception as e:
                    logger.error(f"[yapo] Error cargando detalle id={aviso_id}: {e}")
                    fail_logs.append(FailLog(etapa="ingesta", motivo=str(e), id_externo=aviso_id))
                    continue

                km_raw = self._get_attr(attrs, "Kilómetros", "Kilometros", "Kilometraje")
                precio_raw = self._limpiar_precio(info["precio"])
                km = self._limpiar_km(km_raw) if km_raw else None
                anio_s = self._get_attr(attrs, "Año", "Ano")
                anio = int(anio_s) if anio_s.isdigit() else None
                marca = self._get_attr(attrs, "Marca") or None
                modelo = self._get_attr(attrs, "Modelo") or None
                img_url = attrs.get("imagen_url", "") or None

                logger.debug(f"[yapo] Parseando aviso id={aviso_id}")
                if precio_raw is None:
                    logger.warning(f"[yapo] id={aviso_id} sin precio")
                if km is None:
                    logger.warning(f"[yapo] id={aviso_id} km no encontrado")
                if not marca and not modelo:
                    logger.warning(f"[yapo] id={aviso_id} sin marca ni modelo, título con fallback")

                av_auto = AvisoAuto(
                    fuente=self.fuente,
                    id_externo=aviso_id,
                    url=url,
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

                # Descarga y subida a S3 durante la ingesta
                if self.guardar_raw and carpeta_fotos_raw and carpeta_fotos_processed and img_url:
                    ruta_foto_raw = carpeta_fotos_raw / f"{aviso_id}.jpg"
                    ruta_orig, ruta_avif = await self._descargar_imagen(
                        img_url, ruta_foto_raw, carpeta_fotos_processed, fail_logs, aviso_id
                    )
                    if ruta_orig is not None:
                        fotos_run[aviso_id] = ruta_orig.name
                        s3_ok = await _cargar_a_s3_con_retry(
                            ruta_orig, f"yapo/{fecha_dia}/raw/fotos/{ruta_orig.name}"
                        )
                        if not s3_ok:
                            fail_logs.append(FailLog(
                                etapa="upload_foto_raw",
                                motivo="S3 upload de imagen agotó reintentos",
                                id_externo=aviso_id,
                            ))
                        if ruta_avif is not None:
                            s3_ok_avif = await _cargar_a_s3_con_retry(
                                ruta_avif, f"yapo/{fecha_dia}/processed/fotos/{ruta_avif.name}"
                            )
                            if not s3_ok_avif:
                                fail_logs.append(FailLog(
                                    etapa="upload_foto_processed",
                                    motivo="S3 upload de imagen AVIF agotó reintentos",
                                    id_externo=aviso_id,
                                ))
                    else:
                        fail_logs.append(FailLog(
                            etapa="descarga_foto",
                            motivo="Descarga de imagen fallida",
                            id_externo=aviso_id,
                        ))

                avisos_raw.append(av_auto)

                if self.guardar_raw and ruta_jsonl:
                    ok = _append_avisos_jsonl([av_auto], ruta_jsonl, fotos=fotos_run)
                    if not ok:
                        fail_logs.append(FailLog(
                            etapa="dedup_json",
                            motivo="Error al serializar JSONL",
                            id_externo=aviso_id,
                        ))

            await ctx.close()
            await browser.close()

        logger.info(f"[yapo] Ingesta completa — {len(avisos_raw)} avisos")


        # ── LIMPIEZA (deduplicación por id_externo) ───────────────────────────
        vistos_id: set[str] = set()
        avisos_unicos: list[AvisoAuto] = []
        for av in avisos_raw:
            if av.id_externo in vistos_id:
                logger.warning(f"[yapo] Duplicado detectado id={av.id_externo}, descartando")
                fail_logs.append(FailLog(
                    etapa="dedup_json",
                    motivo="id_externo duplicado entre páginas",
                    id_externo=av.id_externo,
                ))
            else:
                vistos_id.add(av.id_externo)
                avisos_unicos.append(av)

        dups = len(avisos_raw) - len(avisos_unicos)
        logger.info(
            f"[yapo] Deduplicación: {len(avisos_raw)} → {len(avisos_unicos)} únicos"
            f" ({dups} descartados)"
        )


        # ── VALIDACIÓN ────────────────────────────────────────────────────────
        avisos_validos: list[AvisoAuto] = []
        rechazados = 0
        for av in avisos_unicos:
            errores = _validar_aviso(av)
            if errores:
                logger.error(f"[yapo] Aviso rechazado id={av.id_externo}: {errores}")
                fail_logs.append(FailLog(
                    etapa="validacion_json",
                    motivo="; ".join(errores),
                    id_externo=av.id_externo,
                ))
                rechazados += 1
            else:
                avisos_validos.append(av)

        logger.info(
            f"[yapo] Validación: {len(avisos_validos)}/{len(avisos_unicos)} avisos pasan"
            f" ({rechazados} rechazados)"
        )


        # ── PROCESADOS (limpieza + validación superada) ──────────────────────
        if self.guardar_raw and avisos_validos and carpeta:
            ruta_procesados = carpeta / "processed" / "avisos.jsonl"
            ok = _append_avisos_jsonl(avisos_validos, ruta_procesados, fotos=fotos_run)
            if ok:
                logger.info(
                    f"[yapo] {len(avisos_validos)} avisos procesados escritos en {ruta_procesados}"
                )
            else:
                logger.error(f"[yapo] Error al escribir avisos procesados en {ruta_procesados}")

        # ── Metadata JSONL raw → S3 ───────────────────────────────────────────
        if self.guardar_raw and ruta_jsonl and ruta_jsonl.exists():
            metadata_ok = await _cargar_a_s3_con_retry(
                ruta_jsonl,
                f"yapo/{fecha_dia}/raw/avisos.jsonl",
            )
            if not metadata_ok:
                fail_logs.append(FailLog(
                    etapa="upload_metadata",
                    motivo="S3 upload de raw/avisos.jsonl agotó reintentos",
                    id_externo="avisos.jsonl",
                ))

        # ── Processed JSONL → S3 ─────────────────────────────────────────────
        if self.guardar_raw and avisos_validos and carpeta:
            ruta_procesados_jsonl = carpeta / "processed" / "avisos.jsonl"
            if ruta_procesados_jsonl.exists():
                processed_ok = await _cargar_a_s3_con_retry(
                    ruta_procesados_jsonl,
                    f"yapo/{fecha_dia}/processed/avisos.jsonl",
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

        # ── Reporte de ejecución → S3 (siempre, con o sin fallos) ────────────
        if self.guardar_raw and carpeta:
            ruta_reporte = carpeta / "processed" / "run_report.json"
            reporte = {
                "fuente": "yapo",
                "timestamp": inicio.isoformat(),
                "duracion_segundos": round(duracion, 1),
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
                logger.info(
                    f"[yapo] Reporte escrito — {len(fail_logs)} FAIL LOGs, {duracion:.1f}s"
                )
                await _cargar_a_s3_con_retry(
                    ruta_reporte,
                    f"yapo/{fecha_dia}/logs/run_report.json",
                )
            except Exception as e:
                logger.error(f"[yapo] No se pudo escribir run_report.json: {e}")
        elif fail_logs:
            logger.info(
                f"[yapo] {len(fail_logs)} FAIL LOGs generados (guardar_raw=False, no persistidos)"
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
        scraper = ScraperYapoCloud(max_paginas=max_paginas, guardar_raw=True)
        async with AsyncSessionLocal() as sesion:
            resultado = await scraper.ejecutar(sesion)
        logger.info(
            f"[yapo] ejecutar() finalizado — {len(resultado.avisos)} avisos,"
            f" {resultado.errores} errores"
        )

    asyncio.run(_main())
