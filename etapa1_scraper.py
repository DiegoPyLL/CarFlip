"""
CarFlip - Etapa 1: Ingesta de datos
Scraper de avisos de autos desde Yapo.cl y Chileautos.com
Requiere: python -m pip install playwright pandas && python -m playwright install chromium
"""

import csv
import logging
import os
import urllib.request
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# --- Configuracion de rutas ---
BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
RAW_DIR     = os.path.join(BASE_DIR, "data", "raw")
IMGS_DIR    = os.path.join(RAW_DIR, "imagenes")
LOGS_DIR    = os.path.join(BASE_DIR, "logs")
LOG_FILE    = os.path.join(LOGS_DIR, "ingesta.log")
HOY         = datetime.now().strftime("%Y-%m-%d")

os.makedirs(RAW_DIR,  exist_ok=True)
os.makedirs(IMGS_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)

# --- Logger ---
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)

CAMPOS = [
    "fuente", "id_externo", "url", "marca", "modelo", "ano", "precio",
    "kilometraje", "combustible", "transmision",
    "patente", "correo_vendedor", "fecha_aviso", "region",
    "imagen_url", "imagen_local",
]


import re

def extraer_ano(texto):
    match = re.search(r"\b(19[7-9]\d|20[0-2]\d|2030)\b", texto)
    return match.group(0) if match else ""


def limpiar_km(texto):
    """Elimina separadores de miles (punto, apóstrofo, coma) y devuelve solo dígitos."""
    solo_digitos = re.sub(r"[.'`,\s]", "", texto)
    return solo_digitos if solo_digitos.isdigit() else re.sub(r"\D", "", texto)


def normalizar_combustible(valor):
    v = valor.lower().strip()
    if any(w in v for w in ["eléctrico", "electrico", "electric", "ev"]):
        return "electrico"
    if any(w in v for w in ["híbrido", "hibrido", "hybrid"]):
        return "hibrido"
    if any(w in v for w in ["diesel", "diésel"]):
        return "diesel"
    if any(w in v for w in ["bencina", "gasolina", "nafta"]):
        return "bencina"
    return v if v else ""


def normalizar_transmision(valor):
    v = valor.lower().strip()
    if any(w in v for w in ["automát", "automat", "tiptronic", "cvt"]):
        return "automatica"
    if "manual" in v:
        return "manual"
    return v if v else ""


_HEADERS_DESCARGA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.yapo.cl/",
}


def descargar_imagen(url, aviso_id):
    """Descarga la imagen y la guarda en IMGS_DIR. Devuelve la ruta local o '' si falla."""
    if not url:
        return ""
    ext = ".jpg"
    ruta = os.path.join(IMGS_DIR, f"{aviso_id}{ext}")
    if os.path.exists(ruta):
        return ruta
    try:
        req = urllib.request.Request(url, headers=_HEADERS_DESCARGA)
        with urllib.request.urlopen(req, timeout=15) as resp:
            with open(ruta, "wb") as f:
                f.write(resp.read())
        return ruta
    except Exception as e:
        log.warning(f"  imagen no descargada ({aviso_id}): {e}")
        return ""


def limpiar_precio(texto):
    """'$19.590.000\\n-3%' → 19590000 (int) o None si no se puede parsear."""
    if not texto:
        return None
    linea = texto.split("\n")[0]
    solo = re.sub(r"[^\d]", "", linea)
    return int(solo) if solo else None


def guardar_jsonl(fuente, registros):
    import json
    ruta = os.path.join(RAW_DIR, f"{fuente}_{HOY}.jsonl")
    with open(ruta, "w", encoding="utf-8") as f:
        for r in registros:
            anio_raw = r.get("ano", "")
            km_raw   = r.get("kilometraje", "")
            obj = {
                "fuente":            r.get("fuente", fuente),
                "id_externo":        r.get("id_externo", ""),
                "url":               r.get("url", ""),
                "titulo":            (
                    f"{r.get('marca','')} {r.get('modelo','')} "
                    f"{anio_raw} usado precio {r.get('precio','').split(chr(10))[0]}"
                ).strip(),
                "precio":            limpiar_precio(r.get("precio", "")),
                "moneda":            "CLP",
                "marca":             r.get("marca") or None,
                "modelo":            r.get("modelo") or None,
                "anio":              int(anio_raw) if str(anio_raw).isdigit() else None,
                "km":                int(km_raw) if str(km_raw).isdigit() else None,
                "ubicacion":         r.get("region") or None,
                "combustible":       r.get("combustible") or None,
                "descripcion":       None,
                "url_imagen":        r.get("imagen_url") or None,
                "disponible":        True,
                "fecha_publicacion": r.get("fecha_aviso") or None,
            }
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")
    return ruta


def guardar_csv(fuente, registros):
    ruta = os.path.join(RAW_DIR, f"{fuente}_{HOY}.csv")
    with open(ruta, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CAMPOS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(registros)
    return ruta


def safe_text(elemento, selector, default=""):
    try:
        nodo = elemento.query_selector(selector)
        return nodo.inner_text().strip() if nodo else default
    except Exception:
        return default


# ──────────────────────────────────────────────
# Scraper Yapo.cl — dos fases: listado + detalle
# ──────────────────────────────────────────────
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
    // Fallback: extraer desde Schema.org JSON-LD
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
    // Imagen principal: primera URL real del carrusel (formato grande)
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

YAPO_BASE = "https://www.yapo.cl"


def _yapo_recolectar_urls(page, max_paginas):
    """Fase 1: recorre las páginas de listado y devuelve lista de dicts con url y datos básicos."""
    base_url = f"{YAPO_BASE}/region_metropolitana/autos"
    avisos = []

    for pagina in range(1, max_paginas + 1):
        url = f"{base_url}?o={pagina}" if pagina > 1 else base_url
        log.info(f"  [yapo] listado pagina {pagina}: {url}")
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_selector("div.d3-ads-grid", timeout=20000)
        except PWTimeout:
            log.warning(f"  [yapo] timeout en listado pagina {pagina}, continuando...")
            break

        page.wait_for_timeout(2000)
        cards = page.query_selector_all("div.d3-ad-tile")
        log.info(f"  [yapo] pagina {pagina}: {len(cards)} cards")

        for card in cards:
            link = card.query_selector("a[href^='/autos-usados']")
            if not link:
                continue
            href = link.get_attribute("href") or ""
            if not href:
                continue
            avisos.append({
                "url":    YAPO_BASE + href,
                "precio": safe_text(card, "[class*='d3-ad-tile__price']"),
                "region": safe_text(card, "[class*='d3-ad-tile__location']"),
                "fecha":  safe_text(card, "time, [class*='date']") or HOY,
            })

    return avisos


def _get_attr(attrs, *claves):
    """Busca la primera clave que exista en el dict, ignorando tildes en la comparación."""
    import unicodedata
    def normalizar(s):
        return unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode().lower()
    for clave in claves:
        for k, v in attrs.items():
            if normalizar(k) == normalizar(clave) and v:
                return v
    return ""


def scrape_yapo(page, max_paginas=3):
    # Fase 1: URLs del listado — deduplicar para evitar repeticiones por paginación
    avisos_raw = _yapo_recolectar_urls(page, max_paginas)
    vistas = set()
    avisos = []
    for a in avisos_raw:
        if a["url"] not in vistas:
            vistas.add(a["url"])
            avisos.append(a)
    log.info(f"  [yapo] {len(avisos)} avisos unicos a procesar en detalle")

    registros = []
    for i, aviso in enumerate(avisos, 1):
        log.info(f"  [yapo] detalle {i}/{len(avisos)}: {aviso['url']}")
        try:
            page.goto(aviso["url"], wait_until="domcontentloaded", timeout=25000)
            page.wait_for_timeout(1500)
            attrs = page.evaluate(_JS_ATTRS)
        except Exception as e:
            log.warning(f"  [yapo] error en {aviso['url']}: {e}")
            attrs = {}

        km_raw    = _get_attr(attrs, "Kilómetros", "Kilometros", "Kilometraje")
        km        = limpiar_km(km_raw) if km_raw else ""
        img_url   = attrs.get("imagen_url", "")
        aviso_id  = aviso["url"].rstrip("/").split("/")[-1]
        img_local = descargar_imagen(img_url, aviso_id)

        registros.append({
            "fuente":          "yapo",
            "id_externo":      aviso_id,
            "url":             aviso["url"],
            "marca":           _get_attr(attrs, "Marca"),
            "modelo":          _get_attr(attrs, "Modelo"),
            "ano":             _get_attr(attrs, "Año", "Ano"),
            "precio":          aviso["precio"],
            "kilometraje":     km,
            "combustible":     normalizar_combustible(_get_attr(attrs, "Combustible")),
            "transmision":     normalizar_transmision(_get_attr(attrs, "Transmisión", "Transmision")),
            "patente":         "",
            "correo_vendedor": "",
            "fecha_aviso":     aviso["fecha"],
            "region":          aviso["region"],
            "imagen_url":      img_url,
            "imagen_local":    img_local,
        })

        page.wait_for_timeout(1500)

    return registros


# ──────────────────────────────────────────────
# Scraper Chileautos.com
# ──────────────────────────────────────────────
def scrape_chileautos(page, max_paginas=3):
    registros = []
    base_url = "https://www.chileautos.cl/vehiculos/autos/"

    for pagina in range(1, max_paginas + 1):
        url = f"{base_url}?page={pagina}" if pagina > 1 else base_url
        log.info(f"  [chileautos] pagina {pagina}: {url}")

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_selector(
                "[class*='listing-item'], [class*='car-card'], [class*='result']",
                timeout=20000,
            )
        except PWTimeout:
            log.warning(f"  [chileautos] timeout en pagina {pagina}, continuando...")
            break

        cards = page.query_selector_all(
            "[class*='listing-item'], [class*='car-card'], [class*='result-item']"
        )
        log.info(f"  [chileautos] pagina {pagina}: {len(cards)} cards encontradas")

        for card in cards:
            titulo    = safe_text(card, "h2, h3, [class*='title']")
            precio    = safe_text(card, "[class*='price']")
            anio_raw  = safe_text(card, "[class*='year']")
            km_raw    = safe_text(card, "[class*='km'], [class*='mileage'], [class*='odometer']")
            region    = safe_text(card, "[class*='location'], [class*='region'], [class*='city']")
            attrs_raw = safe_text(card, "[class*='feature'], [class*='spec'], [class*='detail']")
            texto_completo = f"{titulo} {attrs_raw}"

            partes = titulo.split()
            marca  = partes[0] if len(partes) > 0 else ""
            modelo = partes[1] if len(partes) > 1 else ""
            anio   = extraer_ano(anio_raw) or extraer_ano(titulo)

            registros.append({
                "fuente":          "chileautos",
                "marca":           marca,
                "modelo":          modelo,
                "ano":             anio,
                "precio":          precio,
                "kilometraje":     limpiar_km(km_raw) if km_raw else "",
                "combustible":     normalizar_combustible(texto_completo),
                "transmision":     normalizar_transmision(texto_completo),
                "patente":         "",
                "correo_vendedor": "",
                "fecha_aviso":     HOY,
                "region":          region,
            })

        page.wait_for_timeout(2000)

    return registros


# ──────────────────────────────────────────────
# Orquestador principal
# ──────────────────────────────────────────────
def main():
    log.info("Inicio ingesta")
    total = 0

    fuentes = [
        ("yapo",       scrape_yapo),
        ("chileautos", scrape_chileautos),
    ]

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
            locale="es-CL",
        )

        for nombre_fuente, fn_scraper in fuentes:
            page = context.new_page()
            # Bloquear imagenes y fuentes para cargar mas rapido
            page.route(
                "**/*.{png,jpg,jpeg,gif,webp,svg,woff,woff2,ttf,otf}",
                lambda route: route.abort(),
            )

            try:
                registros = fn_scraper(page, max_paginas=3)
                ruta_csv   = guardar_csv(nombre_fuente, registros)
                ruta_jsonl = guardar_jsonl(nombre_fuente, registros)
                log.info(f"{nombre_fuente} -> {len(registros)} registros | {ruta_csv} | {ruta_jsonl}")
                total += len(registros)
            except Exception as e:
                log.error(f"{nombre_fuente} -> ERROR: {e}")
            finally:
                page.close()

        context.close()
        browser.close()

    log.info(f"Fin ingesta - total: {total} registros")


if __name__ == "__main__":
    main()