# Scraper Yapo — Guía Completa

Este documento explica **qué hace** el scraper de Yapo, **cómo funciona por dentro** y **cómo usarlo**. Está escrito para que tanto alguien sin experiencia en programación como un desarrollador encuentren lo que necesitan.

---

## ¿Qué hace este scraper? (versión simple)

[yapo.cl](https://www.yapo.cl) es uno de los portales de clasificados más grandes de Chile, donde particulares y automotoras publican autos en venta. Este scraper es un programa que **visita ese sitio automáticamente**, lee los avisos de autos usados de la Región Metropolitana, extrae la información relevante (precio, marca, modelo, año, kilómetros, ubicación, foto) y la guarda en nuestra base de datos para analizarla.

El proceso completo ocurre en cuatro etapas:

```
1. INGESTA      → Visita el sitio y descarga los avisos
2. LIMPIEZA     → Elimina duplicados
3. VALIDACIÓN   → Descarta avisos con datos incorrectos o fuera de rango
4. CARGA        → Guarda los avisos válidos en la base de datos
```

Cada vez que se ejecuta, el scraper guarda también una copia de los datos en disco (archivos JSON y fotos) para auditoría y recuperación ante fallos, y sube ese material a S3.

---

## ¿Por qué este scraper es diferente?

La mayoría de scrapers del proyecto (Autocosmos, Autosusados, etc.) descargan páginas HTML directamente y las procesan. Yapo **no funciona así**: el sitio carga gran parte de su contenido mediante JavaScript, lo que significa que un cliente HTTP normal solo ve una página casi vacía.

Por eso este scraper utiliza **Playwright**, una herramienta que controla un navegador web real (Chromium) de forma automática. El navegador ejecuta el JavaScript del sitio exactamente como lo haría un usuario humano, y una vez que la página está cargada, el scraper extrae los datos desde el DOM ya renderizado.

Esto hace que el scraper sea más lento que los basados en httpx, pero es la única forma confiable de obtener los datos de Yapo sin depender de endpoints internos no documentados.

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
# Sin límite de páginas (recorre toda la sección de autos RM)
.venv\Scripts\python src/carflip/scrapers/Yapo/yapoCloud.py

# Limitado a N páginas (recomendado para pruebas)
.venv\Scripts\python src/carflip/scrapers/Yapo/yapoCloud.py 3
```

### Ejecución desde código Python

```python
import asyncio
from carflip.scrapers.Yapo.yapoCloud import ScraperYapoCloud
from carflip.database.session import AsyncSessionLocal

async def main():
    scraper = ScraperYapoCloud(max_paginas=3, guardar_raw=True)
    async with AsyncSessionLocal() as sesion:
        resultado = await scraper.ejecutar(sesion)
    print(f"{len(resultado.avisos)} avisos válidos, {resultado.errores} errores")

asyncio.run(main())
```

---

## Cómo funciona el pipeline (en detalle)

### Etapa 1 — Ingesta (dos fases)

La ingesta tiene dos fases separadas: primero se recolectan las URLs de los avisos desde las páginas de listado, y luego se visita cada aviso individual para obtener sus datos completos.

#### Fase 1a — Recolección de URLs desde el listado

El scraper abre un navegador Chromium en modo headless (sin ventana visible) y navega por las páginas de listado de autos usados:

```
https://www.yapo.cl/autos-usados.1
https://www.yapo.cl/autos-usados.2
https://www.yapo.cl/autos-usados.3
...
```

Para reducir el tiempo de carga y el consumo de red, el navegador bloquea automáticamente todas las solicitudes de recursos estáticos (imágenes, fuentes, íconos) durante la navegación del listado — solo descarga el HTML y el JavaScript necesarios para renderizar la grilla de avisos.

Por cada página de listado:
1. Espera a que aparezca el selector `div.d3-ads-grid` (la grilla de avisos).
2. Lee todos los cards (`div.d3-ad-tile`) y extrae el enlace al aviso, el precio mostrado, la ubicación y la fecha.
3. Descarta URLs ya vistas (deduplicación temprana por URL).
4. Si la página no tiene resultados, detiene la paginación.
5. Si se alcanza el límite de **1.000 publicaciones** (`_MAX_AVISOS`), detiene la paginación y descarta el excedente.

#### Fase 1b — Extracción de datos en cada aviso

Para cada URL recolectada, el scraper navega a la página de detalle del aviso y ejecuta un **fragmento de JavaScript inyectado** en la página (`page.evaluate()`) que extrae los atributos del auto desde dos fuentes simultáneamente:

- **DOM estructurado**: los elementos `<dt>`/`<dd>` dentro de `.d3-property-insight__attribute-details` contienen los atributos del auto (Marca, Modelo, Año, Kilómetros, Combustible, etc.)
- **JSON-LD embebido**: los tags `<script type="application/ld+json">` de tipo `Car` contienen datos estructurados que complementan lo anterior (útil cuando el DOM omite algún campo).

También extrae la URL de la imagen de portada desde la galería del aviso (buscando `<img>` con el patrón `t_or_fh` en su src).

Por cada aviso, si se encontró una imagen de portada:
1. La descarga con `httpx` (cliente HTTP directo, más eficiente que Playwright para archivos binarios).
2. La convierte a **formato AVIF** usando `image_utils.convertir_a_avif()`.
3. La sube a **S3** con hasta 12 reintentos de 10 minutos cada uno (ventana de 2 horas).

> **¿Por qué AVIF?** Es el formato de imagen moderno más eficiente: misma calidad visual con archivos entre 30% y 50% más pequeños que JPEG. Esto reduce el costo de almacenamiento en Cloudflare R2 y el tiempo de carga en el frontend.

Después de cada aviso se serializa inmediatamente como una línea en el archivo `avisos.jsonl` del run actual (escritura incremental, no se pierde trabajo si el proceso se interrumpe a mitad).

---

### Etapa 2 — Limpieza (deduplicación)

Una vez terminada la ingesta, se recorre la lista completa de avisos y se eliminan duplicados por `id_externo`. Esto puede ocurrir cuando el mismo aviso aparece en distintas páginas del listado durante el mismo run.

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

Los avisos que no superan la validación se registran en el FAIL LOG con `etapa="validacion_json"` e incluyen el motivo exacto del rechazo.

---

### Etapa 4 — FAIL LOG consolidado

Al final del scrape, todos los errores acumulados durante las tres etapas anteriores se escriben en un único archivo `fail_logs.json` dentro de la carpeta `raw/` del run, y se sube a S3.

Cada entrada tiene esta estructura:

```json
{
  "timestamp": "2026-05-16T12:00:00+00:00",
  "etapa": "validacion_json",
  "motivo": "precio 300000 fuera de rango [500.000, 250.000.000] CLP",
  "id_externo": "12345678",
  "fuente": "yapo"
}
```

**Etapas posibles:**

| Etapa | Cuándo se registra |
|---|---|
| `ingesta` | Error al cargar la página de detalle del aviso (timeout, fallo de red) |
| `conversion_avif` | La imagen se descargó pero no se pudo convertir a AVIF |
| `descarga_foto` | La imagen de portada no se pudo descargar |
| `upload_foto` | S3 upload de la imagen agotó los 12 reintentos |
| `upload_metadata` | S3 upload de `raw/avisos.jsonl` agotó los 12 reintentos |
| `upload_processed` | S3 upload de `processed/avisos.jsonl` agotó los 12 reintentos |
| `dedup_json` | Aviso duplicado entre páginas, o error al escribir el JSONL |
| `validacion_json` | Aviso rechazado por validación estructural o semántica |

---

### Etapa 5 — Carga a la base de datos

`scrape()` retorna la lista de `AvisoAuto` válidos. La carga a PostgreSQL la gestiona `ScraperBase.ejecutar()` a través de `uploader.upsert_avisos()`: si el aviso ya existe (misma `id_externo`) lo actualiza; si es nuevo, lo inserta. Los cambios de precio quedan registrados en `precio_anterior` y `delta_pct`.

El resultado de la ejecución (cantidad de avisos, errores, tiempo de inicio y fin) se guarda también en la tabla `scrape_runs`.

---

### Subida de archivos a S3

La función `_cargar_a_s3_con_retry()` sube archivos a S3 via `aioboto3`. Realiza hasta 12 reintentos con intervalos de 10 minutos (2 horas de ventana total). Se invoca en cuatro momentos del pipeline:

1. **Fotos** — inmediatamente después de descargar y convertir cada imagen individual.
2. **`raw/avisos.jsonl`** — al finalizar la ingesta, para dejar el archivo completo del run en S3.
3. **`processed/avisos.jsonl`** — al finalizar la validación, con solo los avisos aprobados.
4. **`fail_logs.json`** — al finalizar el scrape, si hubo errores.

> S3 actúa como almacenamiento intermediario. Desde ahí, el pipeline ETL transfiere las imágenes AVIF a Cloudflare R2 (CDN final), desde donde las consume el frontend.

---

## Datos que se extraen de cada aviso

El scraper mapea la información del sitio al dataclass `AvisoAuto`:

| Campo | Origen | Notas |
|---|---|---|
| `fuente` | — | Siempre `"yapo"` |
| `id_externo` | URL del aviso | Último segmento del path (`/autos-usados/.../12345678` → `"12345678"`) |
| `url` | Enlace del card en el listado | URL directa al aviso en yapo.cl |
| `titulo` | Construido | `"{marca} {modelo} {año} usado precio {precio}"` |
| `precio` | Texto del card de listado | Extracción numérica de la primera línea; resultado en CLP |
| `moneda` | — | Siempre `"CLP"` |
| `marca` | DOM / JSON-LD del detalle | Atributo `"Marca"` en los `<dt>`/`<dd>` del aviso |
| `modelo` | DOM / JSON-LD del detalle | Atributo `"Modelo"` en los `<dt>`/`<dd>` del aviso |
| `anio` | DOM / JSON-LD del detalle | Atributo `"Año"` / `"Ano"` / `modelDate` en JSON-LD |
| `km` | DOM / JSON-LD del detalle | Atributo `"Kilómetros"` / `mileageFromOdometer` en JSON-LD |
| `ubicacion` | Texto del card de listado | Región del aviso |
| `combustible` | DOM / JSON-LD del detalle | Normalizado a: `"bencina"`, `"diesel"`, `"hibrido"`, `"electrico"` |
| `descripcion` | — | No extraído; queda como `None` |
| `url_imagen` | Galería del aviso | Primer `<img>` con `t_or_fh` en su `src` |
| `disponible` | — | Siempre `True` (si aparece en el listado, está activo) |
| `fecha_publicacion` | Texto del card de listado | Texto del elemento `<time>` o fecha actual como fallback |

> **Nota sobre `id_externo`**: se toma directamente del último segmento de la URL del aviso en Yapo (un identificador numérico). A diferencia de Autocosmos, no se genera un hash — Yapo ya provee un ID estable en su estructura de URLs.

> **Nota sobre `combustible`**: los valores que entrega Yapo se normalizan a un vocabulario controlado. Por ejemplo, `"Gasolina"`, `"Nafta"` y `"Bencina"` se convierten todas a `"bencina"`.

---

## Archivos generados en disco

Con `guardar_raw=True` (comportamiento por defecto) se crea una carpeta por ejecución bajo `yapo/`:

```
yapo/
└── {HH-MM-SS_DD-MM-YYYY}/          ← una carpeta por run (hora y fecha)
    ├── raw/
    │   ├── avisos.jsonl             ← todos los avisos del run, uno por línea
    │   ├── fail_logs.json           ← errores consolidados (solo si hubo alguno)
    │   └── fotos/
    │       ├── 12345678.avif        ← imagen de portada en formato AVIF
    │       └── ...
    └── processed/
        └── avisos.jsonl             ← solo los avisos que pasaron limpieza y validación
```

**`raw/avisos.jsonl`**: todos los avisos obtenidos durante la ingesta (incluyendo los que luego serán descartados). Formato JSONL: un objeto JSON por línea, incluye el campo `foto_local` con el nombre del archivo de imagen descargado.

**`raw/fail_logs.json`**: solo se crea si hubo al menos un error durante el run. Es un arreglo JSON con todos los FAIL LOGs del run.

**`processed/avisos.jsonl`**: avisos que superaron la deduplicación y la validación. Estos son los que se cargan a PostgreSQL y se suben a R2.

Con `guardar_raw=False` el scraper sigue funcionando normalmente (scrapea, limpia, valida y carga a la BD) pero no escribe nada en disco ni sube imágenes a S3.

---

## Parámetros del constructor

```python
ScraperYapoCloud(max_paginas=None, guardar_raw=True)
```

| Parámetro | Tipo | Default | Descripción |
|---|---|---|---|
| `max_paginas` | `int \| None` | `None` | Límite de páginas de listado a recorrer. `None` = pagina sin límite de páginas hasta alcanzar 1.000 publicaciones (`_MAX_AVISOS`). Si se especifica un valor, se detiene al llegar al mínimo entre ese número de páginas y 1.000 avisos. Para pruebas usar `3` |
| `guardar_raw` | `bool` | `True` | Si escribe archivos en disco, descarga fotos y sube a S3. No afecta la carga a PostgreSQL |

---

## Configuración (`.env`)

```env
# S3 (almacenamiento intermediario antes de R2)
S3_ACCESS_KEY_ID=tu_access_key
S3_SECRET_ACCESS_KEY=tu_secret_key
S3_REGION=us-east-1
S3_BUCKET=carflip-raw
S3_PREFIX=raw/

# Logging
LOG_LEVEL=INFO
LOG_FILE=logs/carflip.log
```

> El scraper de Yapo no usa `MIN_DELAY_SECONDS` / `MAX_DELAY_SECONDS` del `.env` porque los delays entre avisos los gestiona directamente Playwright con `page.wait_for_timeout()` (1,5 segundos en páginas de detalle, 2 segundos en páginas de listado).

---

## Dependencias

| Paquete | Versión | Propósito |
|---|---|---|
| `playwright` | ≥1.44 | Navegador Chromium headless para ejecutar el JavaScript de Yapo |
| `httpx` | ≥0.27 | Descarga de imágenes de portada (más eficiente que Playwright para binarios) |
| `aioboto3` | ≥12.0 | Cliente S3 asíncrono para subida de fotos y JSONLs |
| `loguru` | ≥0.7 | Logging estructurado con niveles, rotación y colores |
| `pydantic-settings` | ≥2.3 | Lectura de variables de entorno desde `.env` |
| `sqlalchemy[asyncio]` | ≥2.0 | ORM asíncrono para operaciones de base de datos |
| `asyncpg` | ≥0.29 | Driver PostgreSQL asíncrono (requerido por SQLAlchemy async) |

Todas las dependencias se instalan automáticamente con `uv sync` desde la raíz del proyecto. Para Playwright, además hay que instalar el navegador una sola vez:

```bash
playwright install chromium
```

---

## Limitaciones conocidas

- **Límite de 1.000 publicaciones por run**: la constante `_MAX_AVISOS = 1_000` en `yapoCloud.py` controla el tope de avisos recolectados por ejecución. Ajustar ese valor si se necesita más cobertura.
- **Rendimiento más lento que httpx**: al usar un navegador real, cada aviso de detalle tarda ~3–5 segundos en cargar, más 1,5 segundos de espera explícita. Con 1.000 avisos el scrape completo puede tardar entre 90 y 120 minutos.
- **JavaScript dependiente del DOM de Yapo**: si Yapo rediseña su interfaz y cambia los selectores (`.d3-ad-tile`, `.d3-property-insight__attribute-details`, etc.), el scraper dejará de extraer datos correctamente. Actualizar el script `_JS_ATTRS` y los selectores de Playwright en `scrape()`.
- **`fecha_publicacion` con fallback a fecha actual**: Yapo no siempre muestra la fecha de publicación de forma parseable. Cuando el elemento `<time>` no está disponible o su texto no es una fecha, se usa la fecha del día del run como fallback.

---

## Archivos del módulo

```
src/carflip/scrapers/Yapo/
├── yapoCloud.py   ← Pipeline completo (ingesta, limpieza, validación, carga)
├── __init__.py    ← Expone ScraperYapoCloud
└── README.md      ← Este archivo
```

**Módulo principal:** [yapoCloud.py](yapoCloud.py)
**Clase principal:** `ScraperYapoCloud`
**Tabla en PostgreSQL:** `yapo_listings`
