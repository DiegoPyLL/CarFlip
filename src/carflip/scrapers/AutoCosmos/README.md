# Scraper Autocosmos — Guía Completa

Este documento explica **qué hace** el scraper de Autocosmos, **cómo funciona por dentro** y **cómo usarlo**. Está escrito para que tanto alguien sin experiencia en programación como un desarrollador encuentren lo que necesitan.

---

## ¿Qué hace este scraper? (versión simple)

[autocosmos.cl](https://www.autocosmos.cl) es un portal chileno donde particulares y automotoras publican autos en venta. Este scraper es un programa que **visita ese sitio automáticamente**, lee los avisos de autos usados publicados, extrae la información relevante (precio, marca, modelo, año, kilómetros, ubicación, foto) y la guarda en nuestra base de datos para analizarla.

El proceso completo ocurre en cuatro etapas:

```
1. INGESTA      → Visita el sitio y descarga los avisos
2. LIMPIEZA     → Elimina duplicados
3. VALIDACIÓN   → Descarta avisos con datos incorrectos o fuera de rango
4. CARGA        → Guarda los avisos válidos en la base de datos
```

Cada vez que se ejecuta, el scraper guarda también una copia de los datos en disco (archivos JSON y fotos) para auditoría y recuperación ante fallos, y sube ese material a Cloudflare R2.

---

## ¿Por qué existe este módulo?

Autocosmos no ofrece una API oficial para obtener sus datos. Este scraper simula el comportamiento de un navegador humano: visita las páginas de listado una por una, lee el HTML y extrae la información relevante. Está diseñado para ser respetuoso con el sitio: introduce pausas aleatorias entre solicitudes y rota el identificador de navegador (User-Agent) para no sobrecargar los servidores.

---

## Uso

### Integrado al sistema (producción)

El scraper se registra en `runner.py` y se ejecuta automáticamente junto con los demás scrapers del proyecto.

```bash
carflip run      # ejecuta todos los scrapers una vez
carflip start    # inicia el scheduler automático (cada 6 horas)
```

### Ejecución independiente desde la línea de comandos

Útil para pruebas o para correr solo este scraper sin levantar el sistema completo.

```bash
# Sin límite de páginas (recorre todo el sitio)
.venv\Scripts\python src/carflip/scrapers/AutoCosmos/autocosmosCloud.py

# Limitado a N páginas (recomendado para pruebas)
.venv\Scripts\python src/carflip/scrapers/AutoCosmos/autocosmosCloud.py 5
```

### Ejecución desde código Python

```python
import asyncio
from carflip.scrapers.AutoCosmos.autocosmosCloud import ScraperAutocosmosCloud
from carflip.database.session import AsyncSessionLocal

async def main():
    scraper = ScraperAutocosmosCloud(max_paginas=3, guardar_raw=True)
    async with AsyncSessionLocal() as sesion:
        resultado = await scraper.ejecutar(sesion)
    print(f"{len(resultado.avisos)} avisos válidos, {resultado.errores} errores")

asyncio.run(main())
```

---

## Cómo funciona el pipeline (en detalle)

### Etapa 1 — Ingesta

El scraper visita las páginas de listado de autos usados en:

```
https://www.autocosmos.cl/auto/usado?pidx=1
https://www.autocosmos.cl/auto/usado?pidx=2
...
```

Por cada página:

1. **Descarga el HTML** con `httpx` (cliente HTTP asíncrono). Si la descarga falla, reintenta hasta **10 veces** esperando 2 segundos entre intentos. Si se agotan los reintentos, salta a la siguiente página y continúa.
2. **Parsea los cards de avisos** usando BeautifulSoup con el motor lxml. Cada card es un enlace `<a>` cuya URL tiene el formato `/auto/usado/{marca}/{modelo}/{año}/{id_numerico}`.
3. **Deduplica por URL** durante la paginación: si un aviso aparece en más de una página, solo se procesa la primera vez.
4. **Descarga las imágenes** de portada de todos los avisos de la página en paralelo, antes de avanzar a la siguiente página.
5. **Sube las imágenes a Cloudflare R2** inmediatamente después de descargarlas (hasta 12 reintentos con 10 minutos de intervalo entre ellos — ventana de 2 horas).
6. **Guarda en disco** los avisos de la página como una nueva línea en `avisos.jsonl` (formato JSONL: un objeto JSON por línea).

La paginación se detiene cuando una página no contiene ningún aviso, o cuando se alcanza el límite `max_paginas` si fue configurado.

**Rotación de User-Agent**: en cada solicitud HTTP se selecciona aleatoriamente un identificador de navegador distinto usando `fake-useragent`, para reducir el riesgo de bloqueo.

**Delays entre páginas**: entre página y página se espera un tiempo aleatorio entre `MIN_DELAY_SECONDS` y `MAX_DELAY_SECONDS` (configurables en `.env`).

---

### Etapa 2 — Limpieza (deduplicación)

Una vez terminada la ingesta, se recorre la lista completa de avisos y se eliminan duplicados por `id_externo`. Esto puede ocurrir cuando el mismo aviso aparece en distintas páginas del sitio en el mismo run.

Los avisos descartados se registran en el FAIL LOG con `etapa="dedup_json"`.

---

### Etapa 3 — Validación

Cada aviso pasa por una validación de dos niveles antes de ser aceptado:

**Validación estructural** (formato correcto):

| Campo | Regla |
|---|---|
| `anio` | Entero de exactamente 4 dígitos |
| `precio` | Número mayor a 0 |
| `km` | Número mayor o igual a 0 |
| `fecha_publicacion` | Formato `YYYY-MM-DD`, no puede ser una fecha futura |

**Validación semántica** (valores razonables):

| Campo | Rango aceptado |
|---|---|
| `anio` | Entre 1970 y el año actual |
| `precio` | Entre $500.000 y $250.000.000 CLP |

**Advertencia no bloqueante**: si un auto del año 2022 o posterior tiene más de 100.000 km, se registra un `logger.warning`, pero el aviso igual pasa la validación (no se descarta).

Los avisos que no superan la validación se registran en el FAIL LOG con `etapa="validacion_json"` e **incluyen el motivo exacto del rechazo**.

---

### Etapa 4 — FAIL LOG consolidado

Al final del scrape, todos los errores acumulados durante las tres etapas anteriores se escriben en un único archivo `fail_logs.json` dentro de la carpeta `raw/` del run, y se sube a Cloudflare R2.

Cada entrada tiene esta estructura:

```json
{
  "timestamp": "2026-05-16T12:00:00+00:00",
  "etapa": "validacion_json",
  "motivo": "precio 300000 fuera de rango [500.000, 250.000.000] CLP",
  "id_externo": "a3f7c...b2e1",
  "fuente": "autocosmos"
}
```

**Etapas posibles:**

| Etapa | Cuándo se registra |
|---|---|
| `descarga_foto` | La imagen de portada no se pudo descargar |
| `upload_foto` | S3 upload de la imagen agotó los 12 reintentos |
| `upload_metadata` | S3 upload de `avisos.jsonl` agotó los 12 reintentos |
| `dedup_json` | Aviso duplicado entre páginas, o error al escribir el JSONL |
| `validacion_json` | Aviso rechazado por validación estructural o semántica |

---

### Etapa 5 — Carga a la base de datos

`scrape()` retorna la lista de `AvisoAuto` válidos. La carga a PostgreSQL la gestiona `ScraperBase.ejecutar()` a través de `uploader.upsert_avisos()`: si el aviso ya existe (misma `id_externo`) lo actualiza; si es nuevo, lo inserta. Los cambios de precio quedan registrados en `precio_anterior` y `delta_pct`.

El resultado de la ejecución (cantidad de avisos, errores, tiempo de inicio y fin) se guarda también en la tabla `scrape_runs`.

---

### Subida de imágenes a Cloudflare R2

La función `_cargar_a_s3_con_retry()` sube archivos a **Cloudflare R2** via el protocolo S3 compatible. Realiza hasta 12 reintentos con intervalos de 10 minutos (2 horas de ventana total). Se invoca en tres momentos del pipeline:

1. **Fotos** — inmediatamente después de descargar el batch de imágenes de cada página.
2. **`fail_logs.json`** — al finalizar el scrape, si hubo errores.
3. **`avisos.jsonl`** — al finalizar el scrape, para dejar el archivo raw en R2.

---

## Datos que se extraen de cada aviso

El scraper mapea la información del HTML al dataclass `AvisoAuto`:

| Campo | Origen en el HTML | Notas |
|---|---|---|
| `fuente` | — | Siempre `"autocosmos"` |
| `id_externo` | URL completa del aviso | Hash SHA-256 del URL; identifica unívocamente cada aviso |
| `url` | Atributo `href` del card | URL directa al aviso en autocosmos.cl |
| `titulo` | Atributo `alt` de la imagen | Si no hay `alt`, se usa el texto completo del card (máx. 200 chars) |
| `precio` | Texto del card | Regex sobre `$N.NNN`; resultado en CLP |
| `moneda` | — | Siempre `"CLP"` |
| `marca` | Segmento 4 de la URL | Ej. `/auto/usado/ford/...` → `"Ford"` |
| `modelo` | Segmento 5 de la URL | Ej. `/auto/usado/ford/mustang/...` → `"Mustang"` |
| `anio` | Texto del card | Regex `\b(19\|20)\d{2}\b` |
| `km` | Texto del card | Regex sobre `N km` |
| `ubicacion` | Texto del card | Primera parte sin números del texto separado por `\|` |
| `combustible` | — | No disponible en el listado; queda como `None` |
| `descripcion` | — | No disponible en el listado; queda como `None` |
| `url_imagen` | Atributo `src` o `data-src` de `<img>` | Thumbnail de portada del aviso |
| `disponible` | — | Siempre `True` (si aparece en el listado, está activo) |
| `fecha_publicacion` | — | No disponible en el listado; queda como `None` |

> **Nota sobre `id_externo`**: se genera como `sha256(url_completa)` en hexadecimal. Esto garantiza que el identificador sea estable aunque el sitio cambie la estructura numérica interna de sus URLs, mientras la URL canónica del aviso no cambie.

> **Nota sobre `marca` y `modelo`**: se extraen directamente del path de la URL. Si Autocosmos cambia el formato de sus URLs, actualizar el patrón `_PATRON_AVISO` en `autocosmosCloud.py`.

---

## Archivos generados en disco

Con `guardar_raw=True` (comportamiento por defecto) se crea una carpeta por ejecución bajo `autocosmos/`:

```
autocosmos/
└── {HH-MM-SS_DD-MM-YYYY}/          ← una carpeta por run (hora y fecha)
    ├── raw/
    │   ├── avisos.jsonl             ← todos los avisos del run, uno por línea
    │   ├── fail_logs.json           ← errores consolidados (solo si hubo alguno)
    │   └── fotos/
    │       ├── a3f7c...b2e1.jpg     ← imagen de portada, nombre = id_externo
    │       └── ...
    └── processed/
        └── avisos.jsonl             ← solo los avisos que pasaron limpieza y validación
```

**`raw/avisos.jsonl`**: todos los avisos obtenidos durante la ingesta (incluyendo los que luego serán descartados). Formato JSONL: un objeto JSON por línea, incluye el campo `foto_local` con el nombre del archivo de imagen descargado.

**`raw/fail_logs.json`**: solo se crea si hubo al menos un error durante el run. Es un arreglo JSON con todos los FAIL LOGs del run.

**`processed/avisos.jsonl`**: avisos que superaron la deduplicación y la validación. Estos son los que se cargan a PostgreSQL y se suben a R2.

Con `guardar_raw=False` el scraper sigue funcionando normalmente (scrapea, limpia, valida y carga a la BD) pero no escribe nada en disco ni sube imágenes a R2.

---

## Parámetros del constructor

```python
ScraperAutocosmosCloud(max_paginas=None, guardar_raw=True)
```

| Parámetro | Tipo | Default | Descripción |
|---|---|---|---|
| `max_paginas` | `int \| None` | `None` | Límite de páginas a recorrer. `None` = sin límite (recorre hasta que no haya más avisos) |
| `guardar_raw` | `bool` | `True` | Si escribe archivos en disco y descarga fotos. No afecta la carga a la BD |

---

## Configuración (`.env`)

```env
# Delays entre páginas (rate limiting — respetar siempre)
MIN_DELAY_SECONDS=2.0
MAX_DELAY_SECONDS=6.0

# Cloudflare R2 (para subida de fotos, JSONL y fail_logs)
R2_ACCOUNT_ID=tu_account_id
R2_ACCESS_KEY_ID=tu_access_key
R2_SECRET_ACCESS_KEY=tu_secret_key
R2_BUCKET=tu_bucket
```

---

## Dependencias

| Paquete | Versión | Propósito |
|---|---|---|
| `httpx` | ≥0.27 | Cliente HTTP asíncrono para descargar páginas e imágenes |
| `beautifulsoup4` | ≥4.12 | Parseo del HTML de Autocosmos |
| `lxml` | ≥5.2 | Motor rápido para BeautifulSoup (más rápido que el parser nativo) |
| `fake-useragent` | ≥1.5 | Rotación de User-Agent para reducir detección |
| `aioboto3` | ≥12.0 | Cliente S3/R2 asíncrono para subida de imágenes a Cloudflare |
| `loguru` | ≥0.7 | Logging estructurado con niveles, rotación y colores |
| `pydantic-settings` | ≥2.3 | Lectura de variables de entorno desde `.env` |
| `sqlalchemy[asyncio]` | ≥2.0 | ORM asíncrono para operaciones de base de datos |
| `asyncpg` | ≥0.29 | Driver PostgreSQL asíncrono (requerido por SQLAlchemy async) |

Todas las dependencias se instalan automáticamente con `uv sync` desde la raíz del proyecto.

---

## Limitaciones conocidas

- **Solo autos usados públicos**: el scraper cubre únicamente la sección `/auto/usado`. No scrapea nuevos, ni comerciales, ni otras categorías.
- **Sin detalle de aviso**: `combustible`, `descripcion` y `fecha_publicacion` no están disponibles en el listado de cards. Para obtenerlos habría que visitar la página individual de cada aviso (no implementado; aumentaría significativamente el tiempo de scrape y la carga al servidor).
- **`marca` y `modelo` desde la URL**: si Autocosmos cambia el formato de sus URLs, el parseo fallará silenciosamente (quedarán como `None`). Actualizar `_PATRON_AVISO` si esto ocurre.
- **Sin retry de páginas saltadas**: si una página agota sus 10 reintentos y se salta, esos avisos no se recuperan en el run actual.

---

## Archivos del módulo

```
src/carflip/scrapers/AutoCosmos/
├── autocosmosCloud.py   ← Pipeline completo (ingesta, limpieza, validación, carga)
├── __init__.py          ← Expone ScraperAutocosmosCloud
├── requirements.txt     ← Dependencias para uso standalone
└── README.md            ← Este archivo
```

**Módulo principal:** [autocosmosCloud.py](autocosmosCloud.py)
**Clase principal:** `ScraperAutocosmosCloud`
**Tabla en PostgreSQL:** `autocosmos_listings`
