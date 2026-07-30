# Imagen slim de Python 3.12. Antes era la oficial de Playwright, que traía
# Chromium y sus dependencias de sistema para el scraper de Yapo; sin scrapers,
# lo único que corre acá son las migraciones y `carflip deals`, que solo hablan
# con PostgreSQL y con Groq por HTTP.
FROM python:3.12-slim-bookworm

# Instalar uv para gestión rápida de dependencias
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copiar archivos de dependencias primero para aprovechar caché de capas
COPY pyproject.toml uv.lock ./

# Usar el Python de la imagen base. Sin esto uv descarga su propio intérprete
# en /root (modo 700), donde el usuario no-root del contenedor no puede leerlo.
ENV UV_PYTHON_PREFERENCE=only-system

# Instalar dependencias de producción (sin dev tools)
RUN uv sync --frozen --no-group dev

# Copiar código fuente y configuración de migraciones
COPY src/ ./src/
COPY alembic/ ./alembic/
COPY alembic.ini ./

# Eliminar cachés heredados de la imagen base y del build: contienen wheels
# vulnerables (ej. pip) que no se usan en runtime
RUN rm -rf /root/.cache

# Ejecutar como usuario no-root
RUN useradd -m carflip && chown -R carflip /app
USER carflip

# Por defecto detecta deals y termina (.github/workflows/deals.yml lo dispara)
ENTRYPOINT ["uv", "run", "carflip"]
CMD ["deals"]
