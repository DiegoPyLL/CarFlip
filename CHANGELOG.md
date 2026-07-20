# Changelog

Todos los cambios notables de este proyecto se documentan en este archivo.

El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/)
y el proyecto adhiere a [Semantic Versioning](https://semver.org/lang/es/).

## [0.6.0] - 2026-07-19

### Changed

- Ingesta migrada de AWS EC2 (tmux + APScheduler) a GitHub Actions: workflow `scrape.yml` con cron diario a las 08:00 UTC, `concurrency` sin solape y `.env` generado desde los secrets del repo
- Fotos migradas de S3 + CloudFront a Cloudflare R2, con clave estable `fotos/<fuente>/<id_externo>.avif` — re-scrapear un aviso conocido ya no vuelve a subir la imagen (corrige el crecimiento `días × avisos` de la etapa S3)
- Métricas de corrida (`scrape_runs`/`run_fail_logs`) escritas directo en PostgreSQL al final de cada scraper; ya no pasan por `run_report.json` en S3 ni requieren carga manual
- Scraper Checkeados reescrito contra `GET /api/vehicles` (el sitemap y las páginas por marca topan en 20 resultados); sus tests actualizados al nuevo diseño

### Added

- `@vercel/analytics` en la web (único JavaScript de cliente)
- `og-default.png`: imagen Open Graph por defecto que `Base.astro` ya referenciaba

### Removed

- Todo el código de AWS: `storage/s3_cdn.py`, `storage/migrar_s3_a_r2.py`, `tools/cargar_desde_s3.py`, `tools/cargar_reports_s3.py`
- `scripts/concesionarios_autofin.py` (script standalone ajeno al pipeline, sin referencias)
- `package.json`, `package-lock.json` y `node_modules/` accidentales en la raíz; `node_modules/` agregado a `.gitignore`

## [0.5.0] - 2026-07-19

### Changed

- Web recreada desde cero sobre Astro 7 + Tailwind 4 (antes Astro 5 + Tailwind 3 vía `@astrojs/tailwind`, deprecado): misma funcionalidad y contenidos, 6 dependencias directas (antes 19)
- Renames de Tailwind 4 aplicados: `focus:outline-hidden`, `backdrop-blur-xs`, `rounded-xs`
- `compressHTML: true` explícito (el default `'jsx'` de Astro 7 colapsa espacios entre elementos inline)
- `/dashboard` fuera de la navegación, del sitemap y de `llms.txt`, y con `noindex` (métricas operativas internas)

### Removed

- Dependencias sin uso: stack React completo (`react`, `react-dom`, `@astrojs/react`, `@radix-ui/react-slot`, `class-variance-authority`, `lucide-react`, `@types/react*`), `postgres`, `clsx`, `tailwind-merge` y residuos de shadcn (`components.json`, `cn()`)
- `motion` y sus animaciones de entrada: la web queda con 0 KB de JavaScript de cliente
- Shim `web/src/lib/db.ts` (los imports `@lib/db` resuelven a `lib/db/index.ts`)
- Caché `web/.astro/` fuera del control de versiones

### Security

- `npm audit` pasa de 10 vulnerabilidades (5 high) a 0
- Override `path-to-regexp@6.3.0` (parche de GHSA-9wv6-86v2-598j) mientras `@astrojs/vercel` arrastre `@vercel/routing-utils` con la versión vulnerable
- Deuda anotada: la web usa la service_role key de Supabase solo para lecturas — pendiente migrar a anon key + políticas RLS

## [0.4.0] - 2026-07-13

### Added

- Página web `/dashboard`: KPIs operacionales del pipeline (éxito de extracción vs meta >95%, fotos fallidas por aviso, duración del ciclo, avisos válidos), última corrida por fuente con ritmo (avisos/min), historial de corridas, fallas por etapa, métricas de vehículos (activos por fuente, nuevos 24 h, bajadas de precio 7 d) y deals activos por categoría
- Telemetría de corridas en Supabase: `scrape_runs` ampliada con las métricas del `run_report.json` (duración, páginas procesadas, embudo encontrados→únicos→válidos→rechazados) y nueva tabla `run_fail_logs` con cada FAIL LOG individual (etapa, motivo, id_externo) — migración Alembic 0008
- Herramienta `cargar_reports_s3.py`: carga idempotente de los `run_report.json` desde S3 (o archivos locales con `--local`) hacia `scrape_runs`/`run_fail_logs`, con clave natural (source, started_at)
- Link "Dashboard" en la navegación de la web

## [0.3.0] - 2026-07-11

### Added

- Nueva tabla `deals` en Supabase (migración Alembic 0005): snapshot del aviso + contexto de mercado + evaluación IA
- Script SQL `candidatos.sql`: selecciona outliers de precio contra la mediana de su grupo comparable (marca/modelo/año ±1, con guard de kilometraje) y bajadas de precio significativas
- Cliente Groq (`groq_client.py`, API OpenAI-compatible vía httpx): categoriza cada candidato leyendo la descripción — categoría (`oportunidad_clara` / `buen_precio` / `revisar` / `descartar`), puntaje 0-100, riesgos detectados y resumen
- Orquestador `detector.py` con filtro anti-re-tokenización: no vuelve a llamar al LLM si el precio no cambió y la evaluación es reciente
- Comando `carflip deals` + detección automática al final de cada ciclo de scraping
- Variables de entorno `GROQ_API_KEY` y `GROQ_MODEL`; settings `deal_min_comparables`, `deal_max_candidatos`, `deal_lote_ia`, `deal_recategorizar_dias`
- Tests de deals: cliente Groq (respx), filtro anti-re-tokenización y test de integración de la query SQL

### Changed

- La página web `/deals` ahora lee la tabla `deals` y muestra la evaluación IA (badge de categoría, puntaje, riesgos, precio vs mercado y resumen), con filtros por fuente y categoría
- Los deals ya no dependen del historial de precios (`delta_pct`): aparecen desde la primera corrida al comparar contra el mercado

## [0.2.0] - 2026-06-01

### Added

- Scraper Yapo con Playwright + stealth (`yapoCloud.py`) y tabla `yapo_listings` (migración 0004)
- Arquitectura cloud: ingesta en AWS EC2 (tmux + APScheduler), fotos en S3 + CloudFront, PostgreSQL en Supabase (reemplazada en 0.6.0 por GitHub Actions + Cloudflare R2)

### Removed

- Sistema de credenciales keyring/Fernet/AWS Secrets Manager y tabla `session_cookies` (migración 0003)

## [0.1.0] - 2026-05-11

### Added

- Versión inicial: scraper Autocosmos (httpx + BS4), pipeline de ingesta/validación, PostgreSQL con SQLAlchemy async, CLI con click
