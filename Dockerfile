# Imagen oficial de Playwright para Python — incluye Chromium y todas sus dependencias de sistema
# El tag DEBE coincidir con la versión de "playwright" fijada en uv.lock (ver pyproject.toml),
# si no, el navegador instalado en runtime no calza con el que trae la imagen.
FROM mcr.microsoft.com/playwright/python:v1.59.0-jammy

# Instalar uv para gestión rápida de dependencias
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copiar archivos de dependencias primero para aprovechar caché de capas
COPY pyproject.toml uv.lock ./

# Instalar dependencias de producción (sin dev tools)
RUN uv sync --frozen --no-group dev

# Copiar código fuente y configuración de migraciones
COPY src/ ./src/
COPY alembic/ ./alembic/
COPY alembic.ini ./

# Asegurar que la versión de Playwright en el código coincide con la del sistema
RUN uv run playwright install chromium --with-deps

# Ejecutar como usuario no-root (sin forzar UID: la imagen base de Playwright
# ya usa el 1000 para su propio usuario "pwuser")
RUN useradd -m carflip && chown -R carflip /app
USER carflip

# Por defecto ejecuta un ciclo de scraping y termina
# (.github/workflows/scrape.yml lo dispara)
ENTRYPOINT ["uv", "run", "carflip"]
CMD ["run"]
