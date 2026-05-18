"""
Pipeline cloud completo para Yapo Chile.
"""

import asyncio
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from loguru import logger
from playwright.async_api import async_playwright

from carflip.config import settings
from carflip.database.models import YapoListing
from carflip.scrapers.base import AvisoAuto, ScraperBase

BASE_DIR = Path(__file__).parents[4]
RAW_DIR = BASE_DIR / "data" / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)

YAPO_BASE = "https://www.yapo.cl"
_AÑO_MINIMO = 1970
_PRECIO_MINIMO = 500_000
_PRECIO_MAXIMO = 250_000_000
_PATRON_FECHA = re.compile(r"^\d{4}-\d{2}-\d{2}$")

_R2_MAX_REINTENTOS = 12
_R2_INTERVALO_SEG = 600

_HEADERS_HTTP = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": YAPO_BASE,
}


@dataclass
class FailLog:
    etapa: str
    motivo: str
    id_externo: str
    fuente: str = "yapo"
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


async def _cargar_a_r2_con_retry(ruta_local: Path, clave_r2: str) -> bool:
    import aioboto3
    if not settings.r2_account_id:
        logger.warning("[yapo] R2 no configurado en .env, omitiendo upload")
        return False

    r2_endpoint = f"https://{settings.r2_account_id}.r2.cloudflarestorage.com"
    sesion = aioboto3.Session(
        aws_access_key_id=settings.r2_access_key_id,
        aws_secret_access_key=settings.r2_secret_access_key,
    )
    datos = ruta_local.read_bytes()

    async with sesion.client("s3", endpoint_url=r2_endpoint) as cliente:
        for intento in range(1, _R2_MAX_REINTENTOS + 1):
            try:
                await cliente.put_object(Bucket=settings.r2_bucket, Key=clave_r2, Body=datos)
                await cliente.head_object(Bucket=settings.r2_bucket, Key=clave_r2)
                logger.debug(f"[yapo] R2 upload OK: {clave_r2}")
                return True
            except Exception as exc:
                if intento < _R2_MAX_REINTENTOS:
                    logger.warning(f"[yapo] R2 upload fallido intento {intento}/{_R2_MAX_REINTENTOS}: {exc}. Reintentando.")
                    await asyncio.sleep(_R2_INTERVALO_SEG)
                else:
                    logger.error(f"[yapo] R2 upload agotó reintentos: {clave_r2} — {exc}")
    return False


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

    def _validar_aviso(self, aviso: AvisoAuto) -> list[str]:
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
                errores.append(f"precio {aviso.precio} fuera de rango")

        return errores

    async def _descargar_imagen(self, url: str, ruta: Path) -> bool:
        if not url: return False
        if ruta.exists(): return True
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, headers=_HEADERS_HTTP, timeout=15)
                resp.raise_for_status()
                ruta.write_bytes(resp.content)
            return True
        except Exception as e:
            logger.warning(f"[yapo] No se pudo descargar imagen {ruta.name}: {e}")
            return False

    async def scrape(self) -> list[AvisoAuto]:
        inicio = datetime.now()
        fecha_str = inicio.strftime("%Y%m%d_%H%M%S")
        carpeta = RAW_DIR / f"yapo_{fecha_str}"
        carpeta_fotos = carpeta / "fotos"
        carpeta_fotos.mkdir(parents=True, exist_ok=True)
        ruta_jsonl = carpeta / "avisos.jsonl"

        fail_logs: list[FailLog] = []
        avisos_raw: list[dict] = []
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

            # INGESTA: listado
            base_url = f"{YAPO_BASE}/region_metropolitana/autos"
            for pagina in range(1, 4):  # limit to 3 pages
                url = f"{base_url}?o={pagina}" if pagina > 1 else base_url
                logger.info(f"[yapo] Listado página {pagina}: {url}")
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                    await page.wait_for_selector("div.d3-ads-grid", timeout=20_000)
                except Exception as e:
                    logger.warning(f"[yapo] Timeout en página {pagina}: {e}")
                    break

                await page.wait_for_timeout(2_000)
                cards = await page.query_selector_all("div.d3-ad-tile")

                for card in cards:
                    link = await card.query_selector("a[href^='/autos-usados']")
                    if not link: continue
                    href = await link.get_attribute("href")
                    if not href: continue

                    async def _safe(sel: str) -> str:
                        try:
                            n = await card.query_selector(sel)
                            return (await n.inner_text()).strip() if n else ""
                        except Exception:
                            return ""

                    avisos_info.append({
                        "url": YAPO_BASE + href,
                        "precio": await _safe("[class*='d3-ad-tile__price']"),
                        "region": await _safe("[class*='d3-ad-tile__location']"),
                        "fecha": await _safe("time, [class*='date']") or datetime.now().strftime("%Y-%m-%d"),
                    })

            # INGESTA: detalles
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
                precio = self._limpiar_precio(info["precio"])
                km = self._limpiar_km(km_raw) if km_raw else None
                anio_s = self._get_attr(attrs, "Año", "Ano")
                anio = int(anio_s) if anio_s.isdigit() else None
                img_url = attrs.get("imagen_url", "")
                ruta_foto = carpeta_fotos / f"{aviso_id}.jpg"
                foto_ok = await self._descargar_imagen(img_url, ruta_foto)
                marca = self._get_attr(attrs, "Marca") or None
                modelo = self._get_attr(attrs, "Modelo") or None

                registro = {
                    "fuente": self.fuente,
                    "id_externo": aviso_id,
                    "url": url,
                    "titulo": f"{marca or ''} {modelo or ''} {anio_s} usado precio {info['precio'].split(chr(10))[0]}".strip(),
                    "precio": precio,
                    "moneda": "CLP",
                    "marca": marca,
                    "modelo": modelo,
                    "anio": anio,
                    "km": km,
                    "ubicacion": info["region"] or None,
                    "combustible": self._normalizar_combustible(self._get_attr(attrs, "Combustible")),
                    "url_imagen": img_url or None,
                    "foto_local": ruta_foto.name if foto_ok else None,
                    "disponible": True,
                    "fecha_publicacion": info["fecha"],
                }

                avisos_raw.append(registro)

                try:
                    with open(ruta_jsonl, "a", encoding="utf-8") as f:
                        f.write(json.dumps(registro, ensure_ascii=False) + "\n")
                except Exception as e:
                    fail_logs.append(FailLog(etapa="dedup_json", motivo=f"Error JSONL: {e}", id_externo=registro["id_externo"]))

            await ctx.close()
            await browser.close()

        # LIMPIEZA
        vistos: set[str] = set()
        avisos_unicos: list[dict] = []
        for av in avisos_raw:
            if av["id_externo"] in vistos:
                fail_logs.append(FailLog(etapa="dedup_json", motivo="id_externo duplicado", id_externo=av["id_externo"]))
            else:
                vistos.add(av["id_externo"])
                avisos_unicos.append(av)

        # VALIDACION
        avisos_validos: list[AvisoAuto] = []
        for av in avisos_unicos:
            av_auto = AvisoAuto(
                fuente=av["fuente"],
                id_externo=av["id_externo"],
                url=av["url"],
                titulo=av["titulo"],
                precio=Decimal(av["precio"]) if av["precio"] is not None else None,
                moneda=av["moneda"],
                marca=av["marca"],
                modelo=av["modelo"],
                anio=av["anio"],
                km=av["km"],
                ubicacion=av["ubicacion"],
                combustible=av["combustible"],
                url_imagen=av["url_imagen"],
                disponible=av["disponible"],
                fecha_publicacion=av["fecha_publicacion"]
            )
            errores = self._validar_aviso(av_auto)
            if errores:
                fail_logs.append(FailLog(etapa="validacion_json", motivo="; ".join(errores), id_externo=av["id_externo"]))
            else:
                setattr(av_auto, "_foto_local", av.get("foto_local"))
                avisos_validos.append(av_auto)

        # FAIL LOGS
        if fail_logs:
            ruta_fail = carpeta / "fail_logs.json"
            try:
                ruta_fail.write_text(json.dumps([asdict(fl) for fl in fail_logs], ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception as e:
                logger.error(f"[yapo] No se pudo escribir fail_logs: {e}")

        # CARGA R2
        for av in avisos_validos:
            foto = getattr(av, "_foto_local", None)
            if foto:
                ruta_local = carpeta_fotos / foto
                clave_r2 = f"yapo/fotos/{foto}"
                await _cargar_a_r2_con_retry(ruta_local, clave_r2)

        if ruta_jsonl.exists():
            await _cargar_a_r2_con_retry(ruta_jsonl, f"yapo/metadata/{ruta_jsonl.name}")

        return avisos_validos
