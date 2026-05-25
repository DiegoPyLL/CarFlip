<p align="center">
  <img src="carflip_logo.png" alt="CarFlip" width="100%">
</p>

# CarFlip

Plataforma que agrega avisos de autos en venta desde portales chilenos, normaliza los datos, los almacena en PostgreSQL y detecta oportunidades de compra mediante análisis de historial de precios.

**Stack actual:** Python 3.12 + httpx/Playwright · PostgreSQL (Supabase) · S3 + CloudFront · Astro 5 + Vercel

---

## Arquitectura

```
EC2 + TMUX  (ingesta)
  └─ Scrapers (Autocosmos, Yapo)
       ├─ Fotos raw/AVIF  →  S3  →  CloudFront (CDN)
       └─ Metadata validada  →  PostgreSQL

Vercel  (web)
  └─ Astro 5 SSR
       ├─ Consulta PostgreSQL vía Supabase JS client
       └─ Imágenes desde CloudFront
```

Cada scraper implementa el pipeline completo dentro de `scrape()`:

1. Paginación HTTP (httpx + BS4) o navegación headless (Playwright)
2. Descarga de fotos → `data/raw/fotos/`
3. Conversión a AVIF → `data/processed/fotos/`
4. Upload a S3 con retry (12 × 10 min)
5. Append a `data/raw/avisos.jsonl`
6. Deduplicación → validación → `data/processed/avisos.jsonl`
7. Upload de metadata y `run_report.json` a S3

`ScraperBase.ejecutar()` recibe el resultado y hace upsert en PostgreSQL. Las imágenes AVIF se sirven a la web desde CloudFront (`CDN_BASE_URL`).

---

## Fuentes implementadas

| Fuente     | Técnica                | Tabla PostgreSQL      |
| ---------- | ---------------------- | --------------------- |
| Autocosmos | httpx + BeautifulSoup4 | `autocosmos_listings` |
| Yapo       | Playwright + stealth   | `yapo_listings`       |

> Existe la tabla `mercadolibre_listings` reservada para un scraper futuro vía la API oficial, pero aún no está implementado ni registrado.

---

## Puesta en marcha en EC2

### Requisitos previos

- Instancia EC2 (Amazon Linux 2023, `t3.small` recomendado)
- PostgreSQL externo con base de datos `carflip` creada (p. ej. Supabase)
- Bucket S3 + distribución CloudFront
- (Opcional) Bucket Cloudflare R2 — solo si se usa el script de migración `S3 → R2`

### 1 — Conectarse al servidor

```bash
ssh -i /ruta/a/tu-llave.pem ec2-user@<ip-publica>
```

### 2 — Instalar herramientas base

```bash
sudo dnf update -y
sudo dnf install -y tmux git
```

### 3 — Instalar uv y Python 3.12

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env
uv python install 3.12
```

### 4 — Clonar el repositorio e instalar dependencias

```bash
git clone https://github.com/DiegoPyLL/CarFlip
cd CarFlip
uv sync
uv run playwright install chromium
```

### 5 — Crear `.env`

```bash
nano .env
```

```env
# Base de datos
DATABASE_URL=postgresql+asyncpg://usuario:password@host:5432/carflip
USE_SSL=true

# MercadoLibre API (opcional, para futuro scraper)
MERCADOLIBRE_APP_ID=tu_app_id
MERCADOLIBRE_CLIENT_SECRET=tu_client_secret

# S3 — almacenamiento de fotos (raw + AVIF)
S3_ACCESS_KEY_ID=tu_access_key
S3_SECRET_ACCESS_KEY=tu_secret_key
S3_REGION=us-east-1
S3_BUCKET=carflip-raw
S3_PREFIX=autocosmos/

# CloudFront — CDN que sirve las imágenes a la web
CDN_BASE_URL=https://xxxxxxxxxx.cloudfront.net

# Cloudflare R2 — opcional, solo para el script de migración S3 → R2
R2_ACCOUNT_ID=tu_account_id
R2_BUCKET=carflip-fotos
R2_ACCESS_KEY_ID=tu_r2_access_key
R2_SECRET_ACCESS_KEY=tu_r2_secret_key

# Rate limiting
MIN_DELAY_SECONDS=2.0
MAX_DELAY_SECONDS=6.0

# Scheduler
SCRAPE_INTERVAL_HOURS=24

# Deals
DEAL_THRESHOLD_PCT=15.0

# Logs
LOG_LEVEL=INFO
LOG_FILE=logs/carflip.log
```

`Ctrl+O` → `Enter` → `Ctrl+X` para guardar.

### 6 — Aplicar migraciones

```bash
uv run alembic upgrade head
```

### 7 — Ejecutar en tmux

```bash
tmux new -s carflip
source .venv/bin/activate

# Prueba única
carflip run

# Scheduler automático (cada SCRAPE_INTERVAL_HOURS horas)
carflip start
```

Desconectarse sin detener el proceso: `Ctrl+B` → `D`

Reconectar: `tmux attach -t carflip`

---

## Comandos disponibles

| Comando                                    | Descripción                          |
| ------------------------------------------ | ------------------------------------ |
| `carflip run`                              | Ejecuta todos los scrapers una vez   |
| `carflip run --scraper autocosmos`         | Ejecuta un scraper específico        |
| `carflip start`                            | Inicia el scheduler automático       |
| `carflip market <marca> <modelo> <año>`    | Estadísticas de mercado              |

Los scrapers corren de forma **secuencial** (uno a la vez), con una pausa configurable entre cada uno. Scrapers registrados actualmente: `autocosmos`, `yapo`.

---

## Web (Vercel + Astro)

La web está en `web/` y se despliega en Vercel. Es un proyecto **Astro 5 SSR** (con React + Tailwind) que consulta PostgreSQL vía el cliente JS de Supabase y sirve las imágenes desde CloudFront.

### Levantar en local

**Requisitos:** Node.js 20+

```bash
# 1. Entrar a la carpeta web
cd web

# 2. Instalar dependencias
npm install

# 3. Crear web/.env con las claves de Supabase
```

Contenido de `web/.env`:

```env
SUPABASE_URL=https://<tu-proyecto>.supabase.co
SUPABASE_SERVICE_KEY=<service_role key desde Supabase → Settings → API>
CDN_BASE_URL=https://<tu-distribucion>.cloudfront.net
```

```bash
# 4. Levantar servidor de desarrollo
npm run dev
```

Abrir: http://localhost:4321

> No se necesita PostgreSQL local, Python ni ninguna otra dependencia. Todo conecta directo a Supabase vía HTTPS.

### Variables de entorno en Vercel

Configurar como variables de servidor las mismas tres claves:

```env
SUPABASE_URL=https://<tu-proyecto>.supabase.co
SUPABASE_SERVICE_KEY=<service_role key>
CDN_BASE_URL=https://<tu-distribucion>.cloudfront.net
```

---

## Desarrollo

```bash
uv sync                                            # instalar/actualizar dependencias
alembic upgrade head                               # aplicar migraciones
alembic revision --autogenerate -m "descripcion"  # nueva migración
pytest                                             # correr tests
pytest -x -v tests/test_price_tracker.py          # test específico
```

### Agregar un nuevo scraper

1. Crear `src/carflip/scrapers/NombreSitio/NombreSitioCloud.py` heredando de `ScraperBase`
2. Crear `NuevoSitioListing(ListingMixin, Base)` en `src/carflip/database/models.py`
3. Generar y aplicar migración Alembic
4. Declarar `model_class` y `fuente` en el scraper
5. Registrar en `src/carflip/scheduler/runner.py`
6. Actualizar los 5 archivos de la web (`tipos.ts`, `filtros.ts`, `FiltrosBarra.astro`, `db.ts`, `index.astro`)

Ver checklist completo en [CLAUDE.md](CLAUDE.md).

---

## Resolución de problemas

**`carflip: command not found` al reconectar SSH**

```bash
source .venv/bin/activate
# o sin activar:
.venv/bin/carflip start
```

**Timeouts o errores en Yapo (Playwright)**

Aumentar delays en `.env`:

```env
MIN_DELAY_SECONDS=3.0
MAX_DELAY_SECONDS=8.0
```

---

## Documentación

- [CLAUDE.md](CLAUDE.md) — arquitectura, convenciones y decisiones de diseño
