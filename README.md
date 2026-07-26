<p align="center">
  <img src="carflip_logo.png" alt="CarFlip" width="100%">
</p>

# CarFlip

Plataforma que agrega avisos de autos en venta desde portales chilenos, normaliza los datos, los almacena en PostgreSQL y detecta oportunidades de compra (deals) comparando cada aviso contra su mercado y evaluándolo con IA. Los particulares también publican sus autos directamente en el sitio, y esos avisos se integran como una fuente más.

**Stack actual:** Python 3.12 + httpx/Playwright · PostgreSQL (Supabase) · Cloudflare R2 · Groq (evaluación IA de deals) · Astro 7 + Vercel

---

## Arquitectura

```
GitHub Actions  (ingesta — cron diario)
  └─ Scrapers (Autosusados, Checkeados, Autocosmos, Yapo)
       ├─ Fotos AVIF  →  Cloudflare R2 (CDN)
       ├─ Metadata validada  →  PostgreSQL
       └─ Métricas de la corrida  →  `scrape_runs` / `run_fail_logs`
  └─ Detección de deals (al final de cada ciclo)
       ├─ SQL: outliers de precio vs mediana del grupo comparable
       └─ Groq: categorización IA  →  tabla `deals`

Vercel  (web)
  └─ Astro 7 SSR
       ├─ Consulta PostgreSQL vía Supabase JS client
       ├─ Página /deals con evaluación IA
       ├─ Imágenes desde R2
       └─ Avisos de particulares (cuentas, publicación y moderación)
            ├─ Auth de Supabase  →  cliente anon sujeto a RLS
            ├─ Fotos  →  Supabase Storage
            └─ `particulares_listings` — quinta fuente de /avisos, /mercado y /deals
```

Cada scraper implementa el pipeline completo dentro de `scrape()`:

1. Paginación HTTP (httpx + BS4) o navegación headless (Playwright)
2. Descarga de fotos → `data/raw/fotos/`
3. Conversión a AVIF → `data/processed/fotos/`
4. Upload a R2 con retry (12 × 10 min)
5. Append a `data/raw/avisos.jsonl`
6. Deduplicación → validación → `data/processed/avisos.jsonl`

`ScraperBase.ejecutar()` recibe el resultado, hace upsert en PostgreSQL (por lotes, para no exceder el límite de parámetros de asyncpg) y guarda las métricas de la corrida. Las imágenes AVIF se sirven a la web desde R2 (`CDN_BASE_URL`).

Las fotos se suben con clave estable **`fotos/<fuente>/<id_externo>.avif`**. Como `id_externo` es un hash del URL canónico del aviso, cada aviso ocupa un objeto y solo uno: re-scrapear un aviso ya conocido no vuelve a subir la imagen. Los JSONL se siguen escribiendo en local para depurar una corrida, pero no se suben — PostgreSQL es la fuente de verdad.

Al final de cada ciclo corre la **detección de deals** (`src/carflip/deals/`): una query SQL selecciona candidatos cuyo precio es outlier contra la mediana de su grupo comparable (marca/modelo/año ±1, con guard de kilometraje) y Groq los categoriza leyendo la descripción — categoría (`oportunidad_clara` / `buen_precio` / `revisar` / `descartar`), puntaje 0-100, riesgos y resumen. Un filtro anti-re-tokenización evita volver a llamar al LLM si el precio no cambió y la evaluación es reciente. Un fallo en esta etapa (Groq caído, cuota agotada) no aborta el ciclo de scraping.

---

## Fuentes implementadas

| Fuente      | Técnica               | Tabla PostgreSQL         |
| ----------- | ---------------------- | ------------------------ |
| Autosusados | httpx + BeautifulSoup4 | `autosusados_listings` |
| Checkeados  | httpx + BeautifulSoup4 | `checkeados_listings`  |
| Autocosmos  | httpx + BeautifulSoup4 | `autocosmos_listings`  |
| Yapo        | Playwright + stealth   | `yapo_listings`        |

> Existe la tabla `mercadolibre_listings` reservada para un scraper futuro vía la API oficial, pero aún no está implementado ni registrado.
>
> Económicos (`economicos.cl`) fue descartado: el sitio bloquea el scraping (anti-bot). Su scraper, modelo y tabla fueron eliminados (migración Alembic 0007).

---

## Avisos de particulares

La quinta fuente no la alimenta ningún scraper: son avisos que publican personas con una cuenta en el sitio. `particulares_listings` reproduce `ListingMixin` tal cual, así que la capa de lectura de la web y `candidatos.sql` la tratan como una fuente más, sin código especial.

| Tabla                    | Contenido                                                       |
| ------------------------ | --------------------------------------------------------------- |
| `perfiles`               | Nombre, teléfono, región y comuna. 1:1 con `auth.users`         |
| `particulares_listings`  | El aviso, con `estado` (`publicado`/`pausado`/`vendido`)        |
| `particulares_fotos`     | Hasta 10 fotos por aviso, en el bucket `avisos-particulares`     |
| `contacto_revelaciones`  | Auditoría de qué cuenta pidió el teléfono de qué aviso           |
| `reportes_aviso`         | Denuncias, con `estado` (`pendiente`/`resuelto`/`descartado`)   |

**La autorización vive en la base, no en el código.** Estas cinco tablas las escribe la web con la *anon key* del usuario, sujeta a las políticas RLS de las migraciones `0010` (usuario) y `0011` (administrador). El cliente de `SUPABASE_SERVICE_KEY` sigue existiendo solo para las lecturas públicas —que llevan el filtro de estado explícito— y para eliminar cuentas, que exige la API de administración.

El **rol de administrador** no es una columna: viaja en `app_metadata` del JWT, que solo escribe el servidor de Supabase. Se otorga en **Supabase → Authentication → Users → *usuario* → `app_metadata` = `{"rol":"admin"}`**. Sin él, `/dashboard` redirige a la home y las políticas `*_admin` no devuelven nada.

**Anti-abuso** (la publicación es inmediata, sin cola de revisión): correo confirmado y perfil completo para publicar, 5 avisos activos, 3 creaciones por 24 h, 10 fotos de 2 MB por aviso y 25 revelaciones de contacto al día —que ahora se consumen al abrir el aviso, no al pedir el teléfono—. Los topes están en `web/src/lib/publicaciones/limites.ts`. La defensa reactiva es la bandeja de reportes de `/dashboard`, desde donde se despublica un aviso.

**El teléfono nunca sale en el HTML público:** tener sesión es la única condición para verlo —aparece al abrir el aviso, sin un clic intermedio— y cada revelación queda registrada. Al visitante anónimo no le llega el número ni oculto: en su lugar ve la máscara `+56 9 •••• ••••` y la invitación a entrar, que el detalle repite tres veces.

---

## Ejecución programada (GitHub Actions)

La ingesta corre en GitHub Actions en dos corridas separadas que comparten el mismo `concurrency` group (una a la vez, sin solape):

- **Scrapeo** — [`scrape.yml`](.github/workflows/scrape.yml) se dispara todos los días a las 06:00 UTC (02:00–03:00 en Chile), construye la imagen Docker del repositorio, aplica las migraciones pendientes (`alembic upgrade head`), ejecuta los 4 scrapers en secuencia (`carflip run --scraper all`) y persiste el snapshot de mercado (`carflip snapshot`).
- **Deals** — [`deals.yml`](.github/workflows/deals.yml) se dispara a las 10:00 UTC (4 h después del scrapeo) y corre la detección de deals (`carflip deals`). Al compartir el `concurrency` group con el scrapeo, si este aún no termina la corrida de deals espera en cola hasta que la base quede completa.

### Secrets requeridos

Configurar en **Settings → Secrets and variables → Actions**:

| Secret                                          | Descripción                                                          |
| ----------------------------------------------- | --------------------------------------------------------------------- |
| `DATABASE_URL`                                | `postgresql+asyncpg://...` hacia Supabase                           |
| `R2_ACCOUNT_ID`                               | Account ID de Cloudflare                                              |
| `R2_BUCKET`                                   | Bucket R2 donde se guardan las fotos                                  |
| `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY` | API Token de R2 con permisos de escritura                             |
| `CDN_BASE_URL`                                | Dominio público desde el que se sirven las fotos                     |
| `GROQ_API_KEY`                                | Key de[console.groq.com](https://console.groq.com/keys) para los deals |

El resto de la configuración (delays, umbral de deals, modelo Groq, etc.) usa los defaults de `src/carflip/config.py`.

### Corrida manual

**Actions → Scrape** (o **Deals**) **→ Run workflow**. Los logs de cada corrida quedan en esa misma pestaña; las métricas por scraper (páginas, avisos válidos/rechazados, FAIL LOGs) se escriben automáticamente en las tablas `scrape_runs` y `run_fail_logs`, que alimentan el dashboard de la web.

### Notas operativas

- El cron de GitHub no es exacto: puede demorar algunos minutos en horas de alta carga.
- GitHub deshabilita los workflows programados si el repo pasa 60 días sin commits — se reactivan con un clic en la pestaña Actions.
- Los runners usan rangos de IP compartidos (Azure), más propensos a bloqueos anti-bot que una IP dedicada. Si la tabla `run_fail_logs` empieza a mostrar bloqueos sistemáticos (especialmente en Yapo o Autosusados), la alternativa es correr el mismo workflow en un runner self-hosted.

---

## Ejecución local

**Requisitos:** Python 3.12 + [uv](https://docs.astral.sh/uv/), PostgreSQL externo con base `carflip` (p. ej. Supabase) y un bucket de Cloudflare R2.

```bash
git clone https://github.com/VolutusDevGroup/CarFlip
cd CarFlip
uv sync
uv run playwright install chromium
```

Crear `.env` en la raíz:

```env
# Base de datos
DATABASE_URL=postgresql+asyncpg://usuario:password@host:5432/carflip
USE_SSL=true

# MercadoLibre API (opcional, para futuro scraper)
MERCADOLIBRE_APP_ID=tu_app_id
MERCADOLIBRE_CLIENT_SECRET=tu_client_secret

# Cloudflare R2 — almacenamiento de las fotos AVIF
R2_ACCOUNT_ID=tu_account_id
R2_BUCKET=carflip-fotos
R2_ACCESS_KEY_ID=tu_access_key
R2_SECRET_ACCESS_KEY=tu_secret_key

# Dominio público desde el que R2 sirve las imágenes
CDN_BASE_URL=https://img.carflip.cl

# Rate limiting
MIN_DELAY_SECONDS=2.0
MAX_DELAY_SECONDS=6.0

# Scheduler
SCRAPE_INTERVAL_HOURS=24

# Deals
DEAL_THRESHOLD_PCT=15.0

# Groq — categorización IA de deals (key en https://console.groq.com/keys)
GROQ_API_KEY=tu_groq_api_key
GROQ_MODEL=llama-3.3-70b-versatile

# Logs
LOG_LEVEL=INFO
LOG_FILE=logs/carflip.log
```

```bash
uv run alembic upgrade head   # aplicar migraciones
uv run carflip run            # ciclo único
```

También se puede correr con Docker, igual que en CI: `docker compose -f docker/docker-compose.yml up --build`.

---

## Comandos disponibles

| Comando                                    | Descripción                            |
| ------------------------------------------ | --------------------------------------- |
| `carflip run`                            | Ejecuta todos los scrapers una vez      |
| `carflip run --scraper autocosmos`       | Ejecuta un scraper específico          |
| `carflip start`                          | Inicia el scheduler automático         |
| `carflip market <marca> <modelo> <año>` | Estadísticas de mercado                |
| `carflip deals`                          | Detecta y categoriza deals (SQL + Groq) |

Los scrapers corren de forma **secuencial** (uno a la vez), con una pausa configurable entre cada uno. Scrapers registrados actualmente: `autosusados`, `checkeados`, `autocosmos`, `yapo`. La detección de deals ya no corre dentro del ciclo de scrapeo: es un paso aparte (`carflip deals`), programado 4 h después del scrapeo en GitHub Actions.

---

## Web (Vercel + Astro)

La web está en `web/` y se despliega en Vercel bajo el dominio **[carflip.cl](https://carflip.cl)**. Es un proyecto **Astro 7 SSR** (Tailwind 4, sin más JavaScript de cliente que Vercel Analytics) que consulta PostgreSQL vía el cliente JS de Supabase y sirve las imágenes desde Cloudflare R2.

El dominio canónico se declara en `web/astro.config.mjs` (`site`). De ahí lo toman el sitemap, el `<link rel="canonical">` y los metadatos Open Graph del layout `Base.astro`, de modo que los deploys de preview (`*.vercel.app`) no compitan en SEO con el dominio productivo.

Páginas principales: listado con filtros por fuente (`/`), detalle de aviso (`/auto/...`), detalle por marca (`/marcas/...`), estadísticas de mercado (`/mercado`), `/como-funciona`, y `/deals` — oportunidades de compra con la evaluación IA (badge de categoría, puntaje, riesgos, precio vs mercado y resumen), filtrables por fuente y categoría.

### Levantar en local

**Requisitos:** Node.js 22.12+ (requisito de Astro 7)

```bash
# 1. Entrar a la carpeta web
cd web

# 2. Instalar dependencias
npm install

# 3. Usa el .env de la raíz del repo (mismo archivo que el backend Python)
```

El `.env` vive en la raíz del proyecto, no en `web/` — Astro lo lee de ahí vía
`envDir` en `astro.config.mjs`. Debe incluir, además de las variables del
backend:

```env
SUPABASE_URL=https://<tu-proyecto>.supabase.co
SUPABASE_SERVICE_KEY=<service_role key desde Supabase → Settings → API>
CDN_BASE_URL=https://<tu-dominio-r2>
RESEND_API_KEY=<API key desde https://resend.com/api-keys>
CONTACT_EMAIL=<correo donde llegan los mensajes de /contacto>

# Autenticación y avisos de particulares. Sin ellas el sitio público sigue en
# pie y solo se desactiva el inicio de sesión.
PUBLIC_SUPABASE_URL=https://<tu-proyecto>.supabase.co
PUBLIC_SUPABASE_ANON_KEY=<anon/publishable key desde Supabase → Settings → API>
```

> El prefijo `PUBLIC_` es deliberado: la *anon key* está pensada para viajar al cliente y toda su autoridad la acotan las políticas RLS. `SUPABASE_SERVICE_KEY` **nunca** debe llevarlo.

```bash
# 4. Levantar servidor de desarrollo
npm run dev
```

Abrir: http://localhost:4321

> No se necesita PostgreSQL local, Python ni ninguna otra dependencia. Todo conecta directo a Supabase vía HTTPS.

### Variables de entorno en Vercel

Configurar como variables de servidor, en Production y Preview:

```env
SUPABASE_URL=https://<tu-proyecto>.supabase.co
SUPABASE_SERVICE_KEY=<service_role key>
CDN_BASE_URL=https://<tu-dominio-r2>
RESEND_API_KEY=<API key de Resend>
CONTACT_EMAIL=<correo donde llegan los mensajes de /contacto>
PUBLIC_SUPABASE_URL=https://<tu-proyecto>.supabase.co
PUBLIC_SUPABASE_ANON_KEY=<anon/publishable key>
```

Además, en **Supabase → Authentication → URL Configuration**, `https://carflip.cl/api/auth/callback` y `http://localhost:4321/api/auth/callback` deben estar en *Redirect URLs*, o el login por enlace mágico y por Google vuelve con error.

---

## Desarrollo

```bash
uv sync                                            # instalar/actualizar dependencias
alembic upgrade head                               # aplicar migraciones
alembic revision --autogenerate -m "descripcion"  # nueva migración
pytest                                             # correr tests
pytest -x -v tests/BD/test_price_tracker.py       # test específico
```

### Agregar un nuevo scraper

1. Crear `src/carflip/scrapers/NombreSitio/NombreSitioCloud.py` heredando de `ScraperBase`
2. Crear `NuevoSitioListing(ListingMixin, Base)` en `src/carflip/database/models.py`
3. Generar y aplicar migración Alembic
4. Declarar `model_class` y `fuente` en el scraper
5. Registrar en `src/carflip/scheduler/runner.py`
6. Actualizar los 5 puntos de la web (`tipos.ts`, `filtros.ts`, `FiltrosBarra.astro`, `lib/db/`, `index.astro`)

---

## Resolución de problemas

**Timeouts o errores en Yapo (Playwright)**

Aumentar delays en `.env`:

```env
MIN_DELAY_SECONDS=3.0
MAX_DELAY_SECONDS=8.0
```

**El workflow programado dejó de correr**

GitHub deshabilita el cron tras 60 días sin commits en el repo. Reactivarlo en **Actions → Scrape → Enable workflow**.

---

## Documentación

- [CLAUDE.md](CLAUDE.md) — principios de desarrollo del proyecto (simpleza, rendimiento, SEO)
- [web/README.md](web/README.md) — stack y estructura de la web
- [CHANGELOG.md](CHANGELOG.md) — historial de versiones
