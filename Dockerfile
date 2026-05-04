# Imagen oficial de Playwright para Python — incluye Chromium y todas sus dependencias de sistema
FROM mcr.microsoft.com/playwright/python:v1.44.0-jammy

# Instalar uv para gestión rápida de dependencias
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copiar archivos de dependencias primero para aprovechar caché de capas
COPY pyproject.toml uv.lock ./

# Instalar dependencias de producción (sin keyring ni dev tools)
RUN uv sync --frozen --no-group local --no-group dev

# Copiar código fuente y configuración de migraciones
COPY src/ ./src/
COPY alembic/ ./alembic/
COPY alembic.ini ./

# Asegurar que la versión de Playwright en el código coincide con la del sistema
RUN uv run playwright install chromium --with-deps

# Ejecutar como usuario no-root
RUN useradd -m -u 1000 carflipper && chown -R carflipper /app
USER carflipper

# Por defecto ejecuta un ciclo de scraping y termina (EventBridge dispara esto cada 6h)
ENTRYPOINT ["uv", "run", "carflipper"]
CMD ["run"]
