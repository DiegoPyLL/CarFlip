# Despliegue en AWS EC2

Este documento explica paso a paso cómo configurar desde cero una instancia EC2 (con Ubuntu) para correr los scrapers de CarFlip, incluyendo la instalación de Python, base de datos, y configuración para que corra en segundo plano con `tmux`.

---

## 1. Conexión a la Instancia

Conéctate a tu servidor mediante SSH. Si estás en Windows y usas un archivo `.ppk`, puedes usar PuTTY o convertir la llave a `.pem` usando PuTTYgen.

```bash
ssh -i /ruta/a/tu-llave.pem ubuntu@<ip-de-tu-instancia>
```

---

## 2. Instalación de Dependencias del Sistema

Actualiza el sistema e instala las herramientas base (PostgreSQL, tmux, curl y git):

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y postgresql postgresql-contrib tmux curl git chromium-browser
```
*(Nota: `chromium-browser` se instala para que Playwright tenga un navegador de respaldo compatible si falla su propia instalación en sistemas muy nuevos como Ubuntu 26.04).*

---

## 3. Instalación de Python via `uv`

Dado que algunas versiones de Ubuntu no traen Python 3.12 por defecto en sus repositorios `apt`, usaremos `uv` (el gestor de paquetes del proyecto) para instalar y gestionar Python automáticamente.

```bash
# 1. Instalar uv
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env

# 2. Descargar e instalar Python 3.12
uv python install 3.12
```

---

## 4. Configuración de Base de Datos (PostgreSQL)

Crea el usuario y la base de datos para CarFlip. Reemplaza `'tu_password'` por una contraseña segura.

```bash
# Cambiar al usuario administrador de postgres
sudo -i -u postgres

# Crear usuario y BD
psql -c "CREATE USER usuario WITH PASSWORD 'tu_password';"
psql -c "CREATE DATABASE carflip;"
psql -c "GRANT ALL PRIVILEGES ON DATABASE carflip TO usuario;"
psql -c "ALTER DATABASE carflip OWNER TO usuario;"

# Salir de la sesión de postgres
exit
```

---

## 5. Descarga y Configuración del Proyecto

Clona tu repositorio y deja que `uv` instale todas las dependencias (usará el Python 3.12 que instalamos antes):

```bash
git clone <url-de-tu-repositorio>
cd carflip
uv sync
```

Crea y edita el archivo de variables de entorno:

```bash
nano .env
```

Pega el siguiente contenido (ajustando la contraseña de BD y tus credenciales de MercadoLibre):

```env
# Base de datos
DATABASE_URL=postgresql+asyncpg://usuario:tu_password@localhost:5432/carflip

# MercadoLibre API
MERCADOLIBRE_APP_ID=tu_app_id
MERCADOLIBRE_CLIENT_SECRET=tu_client_secret

# Delays entre requests (rate limiting)
MIN_DELAY_SECONDS=2.0
MAX_DELAY_SECONDS=6.0

# Scheduler
SCRAPE_INTERVAL_HOURS=6

# Logging
LOG_LEVEL=INFO
LOG_FILE=logs/carflip.log
```

---

## 6. Inicializar Base de Datos y Playwright

Ejecuta las migraciones para crear las tablas, y asegúrate de que Playwright intente instalar sus navegadores:

```bash
# Crear tablas
alembic upgrade head

# Instalar navegadores de Playwright (puede dar error en Ubuntu 26.04, 
# pero el código ya está configurado para usar el chromium del sistema).
uv run playwright install chromium
```

---

## 7. Ejecución Interactiva y en Segundo Plano

La aplicación cuenta con una consola parametrizada interactiva. 

### Ejecutar Manualmente (con menú interactivo)
Si quieres correr un scraper específico para probar que funcione:
```bash
.venv/bin/carflip run
```
*Esto mostrará un menú para elegir qué scraper ejecutar (0 para todos).* También puedes pasar el parámetro directo: `.venv/bin/carflip run --scraper autocosmosCloud`.

### Correr en Segundo Plano (Scheduler)
Para dejar el scheduler corriendo permanentemente (cada 6 horas), usaremos `tmux`:

```bash
# 1. Crear una nueva sesión
tmux new -s carflip_worker

# 2. Iniciar el programa
.venv/bin/carflip start

# 3. Desconectar y dejar corriendo en el servidor
# Presiona: Ctrl+B, luego presiona D
```

Para volver a ver los logs en vivo después de haber cerrado SSH, conéctate de nuevo y escribe:
```bash
tmux attach -t carflip_worker
```
