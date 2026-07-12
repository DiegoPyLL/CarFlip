# Changelog

Todos los cambios notables de este proyecto se documentan en este archivo.

El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/)
y el proyecto adhiere a [Semantic Versioning](https://semver.org/lang/es/).

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
- Arquitectura free-tier: GitHub Actions (cron) + Supabase PostgreSQL + Cloudflare R2

### Removed

- Sistema de credenciales keyring/Fernet/AWS Secrets Manager y tabla `session_cookies` (migración 0003)

## [0.1.0] - 2026-05-11

### Added

- Versión inicial: scraper Autocosmos (httpx + BS4), pipeline de ingesta/validación, PostgreSQL con SQLAlchemy async, CLI con click
