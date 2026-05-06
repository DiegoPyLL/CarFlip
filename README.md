# CarFlip (TODO(MODIFICAR AL FINAL))

Plataforma integral de inteligencia de mercado automotriz con agregación y análisis de datos en tiempo real desde múltiples portales de venta en Chile.

![CarFlip Logo](carflip_logo.png)

## Propuesta de Valor

CarFlip proporciona una ventaja competitiva mediante:

- **Agregación centralizada de datos**: Unifica precios, características y disponibilidad de vehículos desde MercadoLibre, Yapo, ChileAutos, Facebook Marketplace, etc en una única plataforma
- **Inteligencia de mercado en tiempo real**: Monitoreo continuo cada 6 horas para identificar oportunidades de arbitraje y tendencias de precios
- **Análisis de patrones históricos**: Historial automatizado de precios con cálculo de deltas porcentuales para detección de tendencias
- **Operaciones sin intervención manual**: Scheduler automático que reduce costos operacionales y aumenta la frecuencia de monitoreo
- **Escalabilidad de producción**: Arquitectura async-first diseñada para procesar miles de listados por ciclo sin degradación de rendimiento

## Capacidades Técnicas

| Componente                   | Especificación                                       |
| ---------------------------- | ----------------------------------------------------- |
| Fuentes de datos             | MercadoLibre, Yapo, ChileAutos, Facebook Marketplace  |
| Frecuencia de actualización | Configurable (default: cada 6 horas)                  |
| Historización de datos      | Completa con deltas de precio y timestamps            |
| Disponibilidad               | Ejecución automática sin intervención              |
| Integridad de datos          | Normalización a esquema único, upsert por source+ID |
| Seguridad de credenciales    | Windows Credential Manager + Fernet encryption        |

## Requerimientos

- Python 3.12 o superior
- PostgreSQL 12+ con base de datos `carflip`
- Permisos administrativos (para Windows Credential Manager) o sistema equivalente de keyring

## Instalación

### 1. Preparación del entorno

```bash
# Clonar repositorio
git clone <repo-url>
cd carflip

# Instalar dependencias
uv sync

# Crear base de datos
createdb carflip
```

### 2. Configuración

Crear archivo `.env` en la raíz del proyecto:

```env
DATABASE_URL=postgresql+asyncpg://usuario:password@localhost:5432/carflip
MERCADOLIBRE_APP_ID=tu_app_id
MERCADOLIBRE_CLIENT_SECRET=tu_client_secret
MIN_DELAY_SECONDS=1
MAX_DELAY_SECONDS=3
SCRAPE_INTERVAL_HOURS=6
LOG_LEVEL=INFO
```

### 3. Aplicar esquema de base de datos

```bash
alembic upgrade head
```

### 4. Configurar acceso a fuentes (opcional)

Para portales que requieren autenticación:

```bash
carflip credentials set facebook usuario@email.com tu_password
carflip credentials set yapo usuario@email.com tu_password
```

## Uso

### Ejecución manual de scrapers

```bash
carflip run
```

Ejecuta un ciclo completo de scraping en todas las fuentes y persiste los datos.

### Activar scheduler automático

```bash
carflip start
```

Inicia el servicio de programación automática. El primer ciclo se ejecuta inmediatamente, subsecuentes se ejecutarán cada N horas según `SCRAPE_INTERVAL_HOURS`.

### Gestionar credenciales

```bash
# Listar fuentes con credenciales configuradas
carflip credentials list

# Eliminar credencial de una fuente
carflip credentials delete <source>
```

### Generar reportes de mercado

```bash
carflip market <brand> <model> <year>
```

Ejemplo:

```bash
carflip market Toyota Corolla 2020
```

Retorna estadísticas agregadas: precio promedio, rango, tendencia, volumen de listados.

## Tests

```bash
# Suite completa
pytest

# Test específico con salida detallada
pytest -x -v tests/test_price_tracker.py

# Con cobertura de código
pytest --cov=src/carflip
```

## Arquitectura

### Flujo de Datos

```
Portal Web → HTTP/Playwright → HTML/JSON
    ↓
Parser (BeautifulSoup/JSON decode)
    ↓
Normalización (CarListing dataclass)
    ↓
Persistencia (PostgreSQL upsert)
    ↓
Historial de cambios (price_history)
    ↓
Agregaciones (market statistics)
```

### Patrón de Scrapers

Todos los scrapers heredan de `BaseScraper` en [`src/carflip/scrapers/base.py`](src/carflip/scrapers/base.py). La clase base proporciona:

- Logging automático con niveles configurables
- Medición de tiempo de ejecución
- Manejo de excepciones y recuperación
- Rate limiting con delays aleatorios
- Almacenamiento de estados de ejecución

Implementación requerida:

```python
class TuScraper(BaseScraper):
    async def scrape(self) -> list[CarListing]:
        # Lógica de scraping específica
        # Retorna lista de CarListing normalizados
        pass
```

### Esquema de Base de Datos

| Tabla               | Propósito                                            |
| ------------------- | ----------------------------------------------------- |
| `listings`        | Avisos normalizados (upsert por source + external_id) |
| `price_history`   | Historial de precios con delta porcentual             |
| `scraped_runs`    | Auditoría de ejecuciones por fuente                  |
| `session_cookies` | Cookies de sesión cifradas por fuente                |

## Seguridad

### Gestión de Credenciales

- Passwords: Almacenados exclusivamente en Windows Credential Manager (keyring)
- Cookies de sesión: Cifradas con Fernet, almacenadas en PostgreSQL
- Claves Fernet: Generadas y recuperadas desde el Credential Manager
- Validación: Código verificado para evitar exposición en logs

### Protección Contra Detección y Bloqueo

- User-Agent rotation con fake-useragent
- Delays aleatorios entre requests (configurable)
- Playwright + stealth para sitios con protecciones JavaScript
- Sin paralelización de requests al mismo dominio

### Integridad de Datos

- Todas las queries usan SQLAlchemy ORM con parámetros vinculados
- Nunca concatenación de strings en SQL
- Validación de entrada con Pydantic en todos los puntos de entrada

## Versionamiento

### Versión Semántica

Formato: `MAJOR.MINOR.PATCH`
Versión actual: `0.1.0`

| Incremento | Cuándo                                 |
| ---------- | --------------------------------------- |
| PATCH      | Bug fixes, mejoras de estabilidad       |
| MINOR      | Nuevos scrapers, comandos CLI, features |
| MAJOR      | Breaking changes en CLI o esquema DB    |

### Branching

```
main                          # Rama de producción (siempre estable)
├── feat/descripcion          # Nuevas features
├── fix/descripcion           # Correcciones de bugs
├── chore/descripcion         # Dependencias, config
└── db/descripcion            # Cambios de esquema
```

### Commits (Conventional Commits)

Formato: `<tipo>(<scope>): <descripción>`

Ejemplos válidos:

```
feat(yapo): agregar filtro de año en búsqueda
fix(facebook): manejar timeout en login
chore: actualizar httpx a 0.28
db: agregar índice compuesto source+brand+model
test(market): agregar test de detección de deals
```

## Contribución

### Proceso de Integración

1. Crear rama de trabajo desde `main`:

   ```bash
   git checkout -b feat/descripcion
   ```
2. Implementar cambios siguiendo [CLAUDE.md](CLAUDE.md):

   - Type hints en todas las funciones
   - Logging con loguru (nunca print)
   - Tests para funcionalidad nueva
   - Migraciones Alembic para cambios de schema
3. Validar localmente:

   ```bash
   uv sync
   alembic upgrade head
   pytest
   carflip run
   ```
4. Push a repositorio remoto:

   ```bash
   git push origin feat/descripcion
   ```
5. Crear Pull Request para revisión

### Estándares de Código

- **Type hints obligatorios** en todas las funciones y variables públicas
- **Logging exclusivo** con loguru; prohibido print() en src/
- **Testing requerido** para funcionalidad nueva o cambios en comportamiento
- **Migraciones Alembic** para todos los cambios de esquema DB
- **Documentación interna** en CLAUDE.md para decisiones arquitectónicas

## Documentación

- [CLAUDE.md](CLAUDE.md) — Referencia completa de arquitectura, convenciones y desarrollo
- `src/carflip/scrapers/` — Implementaciones de scrapers como referencia
- `tests/` — Suite de tests y fixtures

## Resolución de Problemas

### PostgreSQL no disponible

```bash
# Windows (si está instalado):
pg_ctl -D "C:\Program Files\PostgreSQL\data" start

# O usando Docker:
docker run --name carflip-db -e POSTGRES_PASSWORD=pass -p 5432:5432 -d postgres
createdb -h localhost -U postgres carflip
```

### Intérprete Python no detectado en VS Code

Seleccionar manualmente el intérprete:

1. `Ctrl+Shift+P` → "Python: Select Interpreter"
2. Seleccionar `.venv\Scripts\python.exe`

### Timeouts en Playwright

Aumentar los delays configurados en `.env`:

```env
MIN_DELAY_SECONDS=3
MAX_DELAY_SECONDS=5
```

---

**CarFlip — Inteligencia de Mercado Automotriz**

Para documentación técnica completa, consulte [CLAUDE.md](CLAUDE.md).
