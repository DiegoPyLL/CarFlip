"""
CarFlip - Yapo.cl Scraper
Pipeline: INGESTA → LIMPIEZA → VALIDACIÓN → CARGA
Misma estructura que autocosmosCloud.py.
"""

import json
import re
import time
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# ── RUTAS ─────────────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent
RAW_DIR  = BASE_DIR / "data" / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)

# ── CONSTANTES ────────────────────────────────────────────────────────────────

FUENTE          = "yapo"
YAPO_BASE       = "https://www.yapo.cl"
_AÑO_MINIMO     = 1970
_PRECIO_MINIMO  = 500_000
_PRECIO_MAXIMO  = 250_000_000
_PATRON_FECHA   = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_R2_MAX_REINTENTOS = 12    # 12 × 10 min = 2 horas
_R2_INTERVALO_SEG  = 600   # 10 minutos

_HEADERS_HTTP = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": YAPO_BASE,
}

# JS que extrae atributos del detalle de un aviso + imagen principal + Schema.org
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
                if (d.vehicleTransmission && !out['Transmision'])
                    out['Transmision'] = d.vehicleTransmission;
                if (d.fuelType && !out['Combustible'])
                    out['Combustible'] = d.fuelType;
                if (d.mileageFromOdometer && !out['Kilometros'])
                    out['Kilometros'] = String(d.mileageFromOdometer.value || '');
                if (d.modelDate && !out['Ano'])
                    out['Ano'] = String(d.modelDate);
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


# ── FAIL LOG ──────────────────────────────────────────────────────────────────


@dataclass
class FailLog:
    etapa:      str
    motivo:     str
    id_externo: str
    fuente:     str = FUENTE
    timestamp:  str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


# ── VALIDACIÓN ────────────────────────────────────────────────────────────────


def _validar_aviso(aviso: dict) -> list[str]:
    """Retorna lista de errores. Lista vacía = aviso válido."""
    errores: list[str] = []
    anio_actual = datetime.now().year

    anio = aviso.get("anio")
    if anio is not None:
        s = str(anio)
        if not (s.isdigit() and len(s) == 4):
            errores.append(f"anio con formato inválido: {anio!r}")

    precio = aviso.get("precio")
    if precio is not None and precio <= 0:
        errores.append(f"precio debe ser > 0, es {precio}")

    km = aviso.get("km")
    if km is not None and km < 0:
        errores.append(f"km debe ser >= 0, es {km}")

    fecha = aviso.get("fecha_publicacion")
    if fecha is not None:
        if not _PATRON_FECHA.match(str(fecha)):
            errores.append(f"fecha_publicacion no es YYYY-MM-DD: {fecha!r}")
        else:
            try:
                f = datetime.strptime(str(fecha), "%Y-%m-%d").date()
                if f > datetime.now().date():
                    errores.append(f"fecha_publicacion es futura: {fecha}")
            except ValueError:
                errores.append(f"fecha_publicacion inválida: {fecha!r}")

    if anio is not None and not any("anio" in e for e in errores):
        if not (_AÑO_MINIMO <= anio <= anio_actual):
            errores.append(f"anio {anio} fuera de rango [{_AÑO_MINIMO}, {anio_actual}]")

    if precio is not None:
        if not (_PRECIO_MINIMO <= precio <= _PRECIO_MAXIMO):
            errores.append(
                f"precio {precio} fuera de rango "
                f"[{_PRECIO_MINIMO:,}, {_PRECIO_MAXIMO:,}] CLP"
            )

    return errores


# ── CARGA R2 ──────────────────────────────────────────────────────────────────


def _cargar_a_r2_con_retry(ruta_local: Path, clave_r2: str) -> bool:
    """
    Sube ruta_local a Cloudflare R2 bajo clave_r2.
    Reintenta cada 10 min por un máximo de 2 horas (12 intentos).
    Retorna True si la carga fue exitosa.
    """
    try:
        import boto3
        from carflip.config import settings
        if not settings.r2_account_id:
            logger.warning("[yapo] R2 no configurado en .env, omitiendo upload")
            return False
    except ImportError:
        logger.warning("[yapo] boto3 no disponible, omitiendo upload R2")
        return False

    r2_endpoint = f"https://{settings.r2_account_id}.r2.cloudflarestorage.com"
    cliente = boto3.client(
        "s3",
        endpoint_url=r2_endpoint,
        aws_access_key_id=settings.r2_access_key_id,
        aws_secret_access_key=settings.r2_secret_access_key,
    )
    datos = ruta_local.read_bytes()

    for intento in range(1, _R2_MAX_REINTENTOS + 1):
        try:
            cliente.put_object(Bucket=settings.r2_bucket, Key=clave_r2, Body=datos)
            cliente.head_object(Bucket=settings.r2_bucket, Key=clave_r2)
            logger.debug(f"[yapo] R2 upload OK: {clave_r2}")
            return True
        except Exception as exc:
            if intento < _R2_MAX_REINTENTOS:
                logger.warning(
                    f"[yapo] R2 upload fallido intento {intento}/{_R2_MAX_REINTENTOS}"
                    f" — {clave_r2}: {exc}. Reintentando en {_R2_INTERVALO_SEG // 60} min."
                )
                time.sleep(_R2_INTERVALO_SEG)
            else:
                logger.error(
                    f"[yapo] R2 upload agotó {_R2_MAX_REINTENTOS} reintentos:"
                    f" {clave_r2} — {exc}"
                )
    return False


# ── HELPERS ───────────────────────────────────────────────────────────────────


def _carpeta_run(fecha_str: str) -> Path:
    carpeta = RAW_DIR / f"yapo_{fecha_str}"
    (carpeta / "fotos").mkdir(parents=True, exist_ok=True)
    return carpeta


def _get_attr(attrs: dict, *claves: str) -> str:
    """Busca la primera clave que exista en attrs, ignorando tildes."""
    import unicodedata

    def norm(s: str) -> str:
        return unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode().lower()

    for clave in claves:
        for k, v in attrs.items():
            if norm(k) == norm(clave) and v:
                return v
    return ""


def _limpiar_km(texto: str) -> int | None:
    solo = re.sub(r"[.'`,\s]", "", texto)
    return int(solo) if solo.isdigit() else None


def _limpiar_precio(texto: str) -> int | None:
    linea = texto.split("\n")[0]
    solo  = re.sub(r"[^\d]", "", linea)
    return int(solo) if solo else None


def _normalizar_combustible(valor: str) -> str | None:
    v = valor.lower().strip()
    if any(w in v for w in ["eléctrico", "electrico", "electric", "ev"]):
        return "electrico"
    if any(w in v for w in ["híbrido", "hibrido", "hybrid"]):
        return "hibrido"
    if any(w in v for w in ["diesel", "diésel"]):
        return "diesel"
    if any(w in v for w in ["bencina", "gasolina", "nafta"]):
        return "bencina"
    return v if v else None


def _normalizar_transmision(valor: str) -> str | None:
    v = valor.lower().strip()
    if any(w in v for w in ["automát", "automat", "tiptronic", "cvt"]):
        return "automatica"
    if "manual" in v:
        return "manual"
    return v if v else None


def _descargar_imagen(url: str, ruta: Path) -> bool:
    if not url:
        return False
    if ruta.exists():
        logger.debug(f"[yapo] Imagen ya existe: {ruta.name}")
        return True
    try:
        req = urllib.request.Request(url, headers=_HEADERS_HTTP)
        with urllib.request.urlopen(req, timeout=15) as resp:
            ruta.write_bytes(resp.read())
        logger.debug(f"[yapo] Imagen descargada: {ruta.name}")
        return True
    except Exception as e:
        logger.warning(f"[yapo] No se pudo descargar imagen {ruta.name}: {e}")
        return False


# ── FASE 1: INGESTA ───────────────────────────────────────────────────────────


def _recolectar_urls(page, max_paginas: int) -> list[dict]:
    """Recorre el listado de Yapo y devuelve lista de {url, precio, region, fecha}."""
    base_url = f"{YAPO_BASE}/region_metropolitana/autos"
    avisos: list[dict] = []

    for pagina in range(1, max_paginas + 1):
        url = f"{base_url}?o={pagina}" if pagina > 1 else base_url
        logger.info(f"[yapo] Listado página {pagina}: {url}")
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            page.wait_for_selector("div.d3-ads-grid", timeout=20_000)
        except PWTimeout:
            logger.warning(f"[yapo] Timeout en listado página {pagina}, deteniendo paginación")
            break

        page.wait_for_timeout(2_000)
        cards = page.query_selector_all("div.d3-ad-tile")
        logger.debug(f"[yapo] Página {pagina}: {len(cards)} cards")

        for card in cards:
            link = card.query_selector("a[href^='/autos-usados']")
            if not link:
                continue
            href = link.get_attribute("href") or ""
            if not href:
                continue
            def _safe(sel: str) -> str:
                try:
                    n = card.query_selector(sel)
                    return n.inner_text().strip() if n else ""
                except Exception:
                    return ""
            avisos.append({
                "url":    YAPO_BASE + href,
                "precio": _safe("[class*='d3-ad-tile__price']"),
                "region": _safe("[class*='d3-ad-tile__location']"),
                "fecha":  _safe("time, [class*='date']") or datetime.now().strftime("%Y-%m-%d"),
            })

    return avisos


def _scrape_detalle(page, aviso_info: dict, carpeta_fotos: Path) -> tuple[dict | None, FailLog | None]:
    """
    Visita la página de detalle de un aviso.
    Retorna (registro_dict, None) si OK, o (None, FailLog) si error fatal.
    """
    url      = aviso_info["url"]
    aviso_id = url.rstrip("/").split("/")[-1]

    try:
        page.goto(url, wait_until="domcontentloaded", timeout=25_000)
        page.wait_for_timeout(1_500)
        attrs = page.evaluate(_JS_ATTRS)
    except Exception as e:
        logger.error(f"[yapo] Error cargando detalle id={aviso_id}: {e}")
        return None, FailLog(etapa="ingesta", motivo=str(e), id_externo=aviso_id)

    km_raw  = _get_attr(attrs, "Kilómetros", "Kilometros", "Kilometraje")
    precio  = _limpiar_precio(aviso_info["precio"])
    km      = _limpiar_km(km_raw) if km_raw else None
    anio_s  = _get_attr(attrs, "Año", "Ano")
    anio    = int(anio_s) if anio_s.isdigit() else None

    img_url   = attrs.get("imagen_url", "")
    ruta_foto = carpeta_fotos / f"{aviso_id}.jpg"
    foto_ok   = _descargar_imagen(img_url, ruta_foto)

    if not foto_ok and img_url:
        logger.warning(f"[yapo] id={aviso_id} imagen no descargada")

    marca  = _get_attr(attrs, "Marca") or None
    modelo = _get_attr(attrs, "Modelo") or None

    return {
        "fuente":            FUENTE,
        "id_externo":        aviso_id,
        "url":               url,
        "titulo":            (
            f"{marca or ''} {modelo or ''} {anio_s} "
            f"usado precio {aviso_info['precio'].split(chr(10))[0]}"
        ).strip(),
        "precio":            precio,
        "moneda":            "CLP",
        "marca":             marca,
        "modelo":            modelo,
        "anio":              anio,
        "km":                km,
        "ubicacion":         aviso_info["region"] or None,
        "combustible":       _normalizar_combustible(_get_attr(attrs, "Combustible")),
        "transmision":       _normalizar_transmision(_get_attr(attrs, "Transmisión", "Transmision")),
        "descripcion":       None,
        "url_imagen":        img_url or None,
        "foto_local":        ruta_foto.name if foto_ok else None,
        "disponible":        True,
        "fecha_publicacion": aviso_info["fecha"],
    }, None


# ── PIPELINE PRINCIPAL ────────────────────────────────────────────────────────


def scrape_yapo(max_paginas: int = 3) -> list[dict]:
    inicio    = datetime.now()
    fecha_str = inicio.strftime("%Y%m%d_%H%M%S")
    carpeta   = _carpeta_run(fecha_str)
    ruta_jsonl = carpeta / "avisos.jsonl"

    fail_logs:   list[FailLog] = []
    avisos_raw:  list[dict]    = []

    logger.info(f"[yapo] Iniciando scrape — {inicio.strftime('%Y-%m-%dT%H:%M:%S')}")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        ctx = browser.new_context(
            user_agent=_HEADERS_HTTP["User-Agent"],
            viewport={"width": 1280, "height": 800},
            locale="es-CL",
        )
        page = ctx.new_page()
        page.route(
            "**/*.{png,jpg,jpeg,gif,webp,svg,woff,woff2,ttf,otf}",
            lambda route: route.abort(),
        )

        # ── INGESTA: listado ──────────────────────────────────────────────────
        avisos_info = _recolectar_urls(page, max_paginas)
        logger.info(f"[yapo] {len(avisos_info)} URLs recolectadas del listado")

        # ── INGESTA: detalles + fotos por página (batch) ──────────────────────
        carpeta_fotos = carpeta / "fotos"
        for i, info in enumerate(avisos_info, 1):
            logger.debug(f"[yapo] Detalle {i}/{len(avisos_info)}: {info['url']}")
            registro, fail = _scrape_detalle(page, info, carpeta_fotos)
            if fail:
                fail_logs.append(fail)
                continue

            avisos_raw.append(registro)

            # Append al JSONL por batch (igual que autocosmosCloud)
            try:
                with open(ruta_jsonl, "a", encoding="utf-8") as f:
                    f.write(json.dumps(registro, ensure_ascii=False) + "\n")
            except Exception as e:
                logger.error(f"[yapo] Error escribiendo JSONL: {e}")
                fail_logs.append(FailLog(
                    etapa="dedup_json",
                    motivo=f"Error JSONL: {e}",
                    id_externo=registro["id_externo"],
                ))

            page.wait_for_timeout(1_500)

        ctx.close()
        browser.close()

    logger.info(
        f"[yapo] Ingesta completa — {len(avisos_raw)} avisos en {max_paginas} páginas"
    )

    # ── LIMPIEZA: deduplicación por id_externo ────────────────────────────────
    vistos: set[str] = set()
    avisos_unicos: list[dict] = []
    for av in avisos_raw:
        if av["id_externo"] in vistos:
            logger.warning(f"[yapo] Duplicado id={av['id_externo']}, descartando")
            fail_logs.append(FailLog(
                etapa="dedup_json",
                motivo="id_externo duplicado",
                id_externo=av["id_externo"],
            ))
        else:
            vistos.add(av["id_externo"])
            avisos_unicos.append(av)

    dups = len(avisos_raw) - len(avisos_unicos)
    logger.info(
        f"[yapo] Deduplicación: {len(avisos_raw)} → {len(avisos_unicos)} únicos"
        f" ({dups} descartados)"
    )

    # ── VALIDACIÓN ────────────────────────────────────────────────────────────
    avisos_validos: list[dict] = []
    rechazados = 0
    for av in avisos_unicos:
        errores = _validar_aviso(av)
        if errores:
            logger.error(f"[yapo] Aviso rechazado id={av['id_externo']}: {errores}")
            fail_logs.append(FailLog(
                etapa="validacion_json",
                motivo="; ".join(errores),
                id_externo=av["id_externo"],
            ))
            rechazados += 1
        else:
            avisos_validos.append(av)

    logger.info(
        f"[yapo] Validación: {len(avisos_validos)}/{len(avisos_unicos)} avisos pasan"
        f" ({rechazados} rechazados)"
    )

    # ── CARGA: FAIL LOGs consolidados ─────────────────────────────────────────
    if fail_logs:
        ruta_fail = carpeta / "fail_logs.json"
        try:
            ruta_fail.write_text(
                json.dumps([asdict(fl) for fl in fail_logs], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            logger.info(f"[yapo] {len(fail_logs)} FAIL LOGs escritos en {ruta_fail}")
        except Exception as e:
            logger.error(f"[yapo] No se pudo escribir fail_logs.json: {e}")

    # ── CARGA: imágenes a R2 ──────────────────────────────────────────────────
    imgs_ok = 0
    for av in avisos_validos:
        if not av.get("foto_local"):
            continue
        ruta_local = carpeta / "fotos" / av["foto_local"]
        clave_r2   = f"yapo/fotos/{av['foto_local']}"
        if _cargar_a_r2_con_retry(ruta_local, clave_r2):
            imgs_ok += 1

    if imgs_ok:
        logger.info(f"[yapo] {imgs_ok} imágenes subidas a R2")

    # ── CARGA: metadata JSON a R2 ─────────────────────────────────────────────
    if ruta_jsonl.exists():
        clave_jsonl = f"yapo/metadata/{ruta_jsonl.name}"
        _cargar_a_r2_con_retry(ruta_jsonl, clave_jsonl)

    duracion = (datetime.now() - inicio).total_seconds()
    logger.info(
        f"[yapo] Scrape finalizado — {len(avisos_validos)} avisos válidos"
        f" listos para carga ({duracion:.1f}s)"
    )

    return avisos_validos


# ── ENTRYPOINT ────────────────────────────────────────────────────────────────


def main() -> None:
    try:
        from carflip.config import settings
        logger.add(settings.log_file, rotation="10 MB", level=settings.log_level, encoding="utf-8")
    except ImportError:
        logger.add("logs/yapo.log", rotation="10 MB", level="INFO", encoding="utf-8")

    avisos = scrape_yapo(max_paginas=3)
    logger.info(f"[yapo] Total avisos válidos: {len(avisos)}")


if __name__ == "__main__":
    main()
