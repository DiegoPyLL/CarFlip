# Changelog

Todos los cambios importantes en este proyecto se documentan en este archivo.

El formato se basa en [Keep a Changelog](https://keepachangelog.com/), y este proyecto sigue [Semantic Versioning](https://semver.org/).

---

## [0.1.0] - 2026-05-04

### Added

- **Arquitectura base del proyecto**
  - Patrón de scrapers con `BaseScraper` que gestiona logging, timing y manejo de errores
  - Normalización de datos a través del dataclass `CarListing`
  - Soporte para scrapers HTTP (httpx + BeautifulSoup4) y headless (Playwright + stealth)
  
- **Scrapers iniciales** (5 fuentes)
  - `yapo.py` — web de compraventa de autos
  - `chileautos.py` — portal de autos de Chile
  - `mercadolibre.py` — MercadoLibre (API oficial)
  - `autosusados.py` — marketplace de autos usados
  - `facebook.py` — Facebook Marketplace con login y Playwright
  
- **Base de datos**
  - ORM async con SQLAlchemy 2.0 + asyncpg
  - Modelos: `Listing`, `PriceHistory`, `ScrapedRun`, `SessionCookie`
  - Migraciones con Alembic (`0001_initial_schema.py`)
  - Cifrado de cookies de sesión con Fernet
  
- **Gestión de credenciales**
  - Almacenamiento seguro de passwords en Windows Credential Manager (keyring)
  - Cifrado de cookies de sesión con Fernet (clave en llavero del OS)
  - Comandos CLI: `credentials set`, `credentials delete`, `credentials list`
  
- **Scheduler**
  - APScheduler para ejecutar scrapers automáticamente cada 6 horas
  - Comando CLI: `carflipper start` para iniciar scheduler
  - Comando CLI: `carflipper run` para scraping manual una sola vez
  
- **CLI principal** (click)
  - `carflipper run` — ejecutar todos los scrapers una vez
  - `carflipper start` — iniciar scheduler automático (cada 6h)
  - `carflipper credentials` — gestionar credenciales
  - `carflipper market` — estadísticas de mercado por marca/modelo/año
  
- **Configuración**
  - `pydantic-settings` para leer desde `.env`
  - Variables de configuración en `config.py`
  - Ejemplo `.env.example` con valores por defecto
  - Soporte para delay entre requests (rate limiting)
  
- **Tests**
  - Framework: pytest + pytest-asyncio + pytest-mock
  - Tests de scrapers base y price tracker
  - Estructura: `tests/` espeja `src/carflipper/`
  
- **Documentación**
  - `CLAUDE.md` — guía detallada de arquitectura, convenciones y seguridad
  - `README.md` — descripción del proyecto y cómo usarlo
  - `.env.example` — plantilla de variables de entorno
  
- **Infraestructura**
  - Docker: `Dockerfile` y `docker-compose.yml` para PostgreSQL
  - Gestión de dependencias con **uv** (Python 3.12+)
  - `.gitignore` con exclusiones apropiadas
  - `.dockerignore` para optimizar imágenes
  
- **Branding**
  - `carflip_logo.png` — logo del proyecto

### Tech Stack

- **Python** 3.12+
- **Web scraping**: httpx, BeautifulSoup4, lxml
- **Headless**: Playwright + playwright-stealth + fake-useragent
- **Base de datos**: SQLAlchemy 2.0 async, asyncpg, Alembic
- **Validación**: pydantic 2, pydantic-settings
- **Scheduler**: APScheduler 3
- **Credenciales**: keyring, cryptography (Fernet)
- **CLI**: click
- **Logging**: loguru
- **Tests**: pytest, pytest-asyncio, pytest-mock
- **Gestor de paquetes**: uv

---

## Notas sobre futuras versiones

### Candidatos para versión 0.2.0
- Nuevos scrapers (más fuentes)
- Mejoras en la interfaz CLI
- Dashboard o API REST para consultar datos
- Alertas de deals (cuando un auto baja de precio significativamente)

### Candidatos para versión 1.0.0
- Schema de base de datos estable (breaking changes deben evitarse)
- CLI interface congelada (cambios serían breaking)
- Cobertura de tests >80%
