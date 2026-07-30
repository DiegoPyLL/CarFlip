<p align="center">
  <img src="carflip_logo.png" alt="CarFlip" width="100%">
</p>

# CarFlip

**Buscar auto usado en Chile significa abrir cinco pestañas y comparar a ojo.** CarFlip junta todos esos avisos en un solo lugar, los ordena y avisa cuáles están baratos de verdad.

👉 **[carflip.cl](https://carflip.cl)**

---

## Qué hace

**Reúne los avisos.** Todos los días, de madrugada, CarFlip revisa cuatro portales chilenos (Autosusados, Checkeados, Autocosmos y Yapo) y guarda los autos nuevos que aparecieron. También cualquier persona puede publicar su auto directamente en el sitio: esos avisos conviven con el resto, sin distinción.

**Ordena la información.** Cada aviso queda con los mismos campos —marca, modelo, año, kilometraje, precio, fotos— aunque el portal de origen los mostrara de otra forma. Eso es lo que permite compararlos entre sí.

**Detecta oportunidades.** CarFlip calcula cuánto vale realmente cada auto: toma todos los avisos parecidos (misma marca, modelo y año, con kilometraje similar) y saca el precio típico. Si uno está bastante por debajo, entra a la página **/deals**.

**Pero un precio bajo no siempre es una ganga.** Puede ser un auto chocado, sin papeles o con el motor malo. Por eso, antes de mostrarlo, una IA lee la descripción del aviso y lo clasifica: *oportunidad clara*, *buen precio*, *revisar* o *descartar*, con un puntaje y los riesgos que detectó.

---

## Cómo está hecho

Son dos piezas que casi no se hablan entre sí. Comparten la base de datos y nada más.

```
1. El recolector (Python)          2. El sitio web (Astro)
   Corre una vez al día en           Vive en Vercel, lee la
   GitHub Actions, sin servidor      base de datos y muestra
   propio ni costo fijo.             los avisos.
              ↓                                ↑
        ┌─────────────────────────────────────────┐
        │   Base de datos PostgreSQL (Supabase)   │
        │   + fotos en Cloudflare R2              │
        └─────────────────────────────────────────┘
```

| Pieza | Qué usa |
| --- | --- |
| Recolector | Python 3.12 · httpx + BeautifulSoup (tres portales) · Playwright (Yapo, que exige navegador real) |
| Base de datos | PostgreSQL en Supabase |
| Fotos | Convertidas a AVIF y guardadas en Cloudflare R2 |
| IA | Groq (Llama 3.3), solo para clasificar oportunidades |
| Web | Astro 7 + Tailwind 4, desplegada en Vercel |

La web casi no lleva JavaScript: se arma en el servidor y llega al navegador como HTML listo. Es la razón de que cargue rápido y de que salga bien posicionada en Google.



## Avisos de particulares

Cualquiera puede crear una cuenta y publicar su auto. Se publica al instante, sin cola de revisión, pero con límites para evitar abusos: correo confirmado, perfil completo, 15 publicaciones por día como máximo, hasta 10 fotos de 2 MB cada una, y patente obligatoria (validada contra los formatos legales chilenos).

Si un aviso es problemático, cualquier visitante puede reportarlo y el administrador lo baja desde el panel interno. Un aviso que pasa 60 días sin tocarse se pausa solo, para que el listado no se llene de autos vendidos hace meses.

**Sobre el teléfono del vendedor:** nunca aparece en el HTML público. Un visitante sin cuenta ve `+56 9 •••• ••••`; hay que iniciar sesión para verlo, y cada vez que alguien lo mira queda registrado. Así el número no termina en manos de un bot recolector de datos.

**Los permisos viven en la base de datos, no en el código.** Aunque alguien salte la interfaz y hable directo con la base, no puede editar avisos ajenos, poner precios negativos ni saltarse los límites: las reglas están escritas ahí abajo, donde no hay forma de rodearlas.

---

## Cuándo corre cada cosa

Dos tareas programadas en GitHub Actions, que nunca se pisan entre sí:

- **06:00 UTC** (~02:00 en Chile) — recolecta los avisos de los portales.
- **10:00 UTC** — cuatro horas después, calcula las oportunidades sobre una base ya completa.

Se pueden lanzar a mano desde **Actions → Scrape** (o **Deals**) **→ Run workflow**. Los resultados de cada corrida —páginas revisadas, avisos válidos, errores— quedan guardados y se ven en el panel interno del sitio.

> Dos detalles del cron de GitHub: puede atrasarse unos minutos en horas peak, y se desactiva solo si el repositorio pasa 60 días sin commits (se reactiva con un clic).

---

## Levantarlo en tu máquina

### Solo la web

Es lo más simple y lo más habitual: no necesitas Python ni base de datos local, todo conecta a Supabase por internet.

**Necesitas:** Node.js 22.12 o superior.

```bash
git clone https://github.com/DiegoPyLL/CarFlip
cd CarFlip/web
npm install
npm run dev
```

Abre http://localhost:4321

El archivo `.env` va en la **raíz** del repositorio, no dentro de `web/`:

```env
SUPABASE_URL=https://<tu-proyecto>.supabase.co
SUPABASE_SERVICE_KEY=<service_role key — Supabase → Settings → API>
CDN_BASE_URL=https://<tu-dominio-de-fotos>
RESEND_API_KEY=<para el formulario de contacto>
CONTACT_EMAIL=<correo donde llegan esos mensajes>

# Cuentas y avisos de particulares.
# Sin estas dos el sitio funciona igual, solo se desactiva el login.
PUBLIC_SUPABASE_URL=https://<tu-proyecto>.supabase.co
PUBLIC_SUPABASE_ANON_KEY=<anon key — Supabase → Settings → API>
```

> El prefijo `PUBLIC_` es a propósito: esa clave está diseñada para llegar al navegador y sus permisos los limita la base de datos. **`SUPABASE_SERVICE_KEY` no debe llevarlo nunca** — esa sí es secreta.

### El recolector

**Necesitas:** Python 3.12, [uv](https://docs.astral.sh/uv/), una base PostgreSQL y un bucket de Cloudflare R2.

```bash
uv sync
uv run playwright install chromium
uv run alembic upgrade head   # crear/actualizar las tablas
uv run carflip run            # una corrida completa
```

Al `.env` hay que agregarle:

```env
DATABASE_URL=postgresql+asyncpg://usuario:password@host:5432/carflip
USE_SSL=true

R2_ACCOUNT_ID=tu_account_id
R2_BUCKET=carflip-fotos
R2_ACCESS_KEY_ID=tu_access_key
R2_SECRET_ACCESS_KEY=tu_secret_key
CDN_BASE_URL=https://img.carflip.cl

GROQ_API_KEY=tu_key            # https://console.groq.com/keys
GROQ_MODEL=llama-3.3-70b-versatile

MIN_DELAY_SECONDS=2.0          # pausa entre peticiones, para no saturar los portales
MAX_DELAY_SECONDS=6.0
DEAL_THRESHOLD_PCT=15.0        # cuánto bajo el mercado para considerarse oportunidad
LOG_LEVEL=INFO
```

El resto de la configuración usa valores por defecto razonables (`src/carflip/config.py`).

También corre en Docker, igual que en CI:

```bash
docker compose -f docker/docker-compose.yml up --build
```

### Comandos

| Comando | Qué hace |
| --- | --- |
| `carflip run` | Recolecta de todos los portales, una vez |
| `carflip run --scraper autocosmos` | Solo uno |
| `carflip start` | Deja el recolector corriendo en bucle |
| `carflip market <marca> <modelo> <año>` | Precios de mercado de un modelo |
| `carflip deals` | Busca y clasifica oportunidades |

Los portales se recorren de a uno, nunca en paralelo, con pausas entre medio.

---

## Desplegar

La web va a Vercel con las mismas variables del `.env` (como variables de servidor, en Production y Preview). El recolector necesita sus claves en **Settings → Secrets and variables → Actions** del repositorio: `DATABASE_URL`, las cuatro de R2, `CDN_BASE_URL` y `GROQ_API_KEY`.

Un paso que se olvida fácil: en **Supabase → Authentication → URL Configuration** hay que agregar `https://carflip.cl/api/auth/callback` y `http://localhost:4321/api/auth/callback` a *Redirect URLs*. Sin eso, el login por Google y por enlace mágico vuelve con error.

---

## Para desarrollar

```bash
uv sync                                           # dependencias del recolector
alembic upgrade head                              # aplicar cambios de base de datos
alembic revision --autogenerate -m "descripcion"  # crear uno nuevo
pytest                                            # tests
```

### Agregar un portal nuevo

1. Crear el scraper en `src/carflip/scrapers/NombreSitio/`, heredando de `ScraperBase`
2. Agregar su tabla en `src/carflip/database/models.py` (usando `ListingMixin`)
3. Generar y aplicar la migración de base de datos
4. Declarar `model_class` y `fuente` en el scraper
5. Registrarlo en `src/carflip/scheduler/runner.py`
6. Sumarlo en la web: `tipos.ts`, `filtros.ts`, `FiltrosBarra.astro`, `lib/db/` e `index.astro`

### Si algo falla

**Yapo da timeouts.** Sube las pausas en el `.env`: `MIN_DELAY_SECONDS=3.0` y `MAX_DELAY_SECONDS=8.0`.

**La tarea programada dejó de correr.** GitHub la desactiva tras 60 días sin commits. Se reactiva en **Actions → Scrape → Enable workflow**.

---

## Más documentación

- [CLAUDE.md](.claude\CLAUDE.md) — los principios con que se toman las decisiones técnicas aquí
- [web/README.md](web/README.md) — detalle de la web
- [CHANGELOG.md](CHANGELOG.md) — qué cambió en cada versión
