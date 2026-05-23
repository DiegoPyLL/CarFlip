# CarFlip

Plataforma que agrega avisos de autos en venta desde múltiples portales chilenos, normaliza los datos y los almacena en una base de datos para detectar oportunidades de compra mediante análisis de precios.

CarFlip está diseñado para correr en la nube. Esta guía cubre todo desde la creación del servidor hasta tenerlo funcionando.

---

## Puesta en marcha desde cero

### Paso 1 — Crear una cuenta en AWS

Entra a [aws.amazon.com](https://aws.amazon.com) y crea una cuenta gratuita si no tienes una. AWS pedirá una tarjeta de crédito para verificar identidad, pero la capa gratuita cubre lo necesario para este proyecto.

---

### Paso 2 — Crear el servidor (instancia EC2)

1. Inicia sesión en la consola de AWS: [console.aws.amazon.com](https://console.aws.amazon.com)
2. En el buscador, escribe **EC2** y selecciónalo
3. Haz clic en **Launch instance** (Lanzar instancia)
4. Configura lo siguiente:

| Campo | Valor recomendado |
|---|---|
| Name | `carflip-server` |
| AMI (sistema operativo) | **Amazon Linux 2023** |
| Instance type | `t2.micro` (capa gratuita) o `t3.small` para mayor rendimiento |
| Key pair | Crear uno nuevo → guarda el archivo `.pem` en tu computador |
| Storage | 20 GB (ajustar según volumen de fotos esperado) |

5. En **Network settings**, asegúrate de que **Allow SSH traffic** esté marcado
6. Haz clic en **Launch instance**

Espera 1-2 minutos hasta que el estado de la instancia diga `Running`.

---

### Paso 3 — Conectarse al servidor

Una vez que la instancia esté corriendo, abre una terminal en tu computador y ejecuta:

```bash
ssh -i /ruta/a/tu-llave.pem ec2-user@<ip-publica-de-la-instancia>
```

La IP pública aparece en la consola de EC2, en la columna **Public IPv4 address**.

> En Windows puedes usar la terminal de VS Code, Git Bash o PowerShell.

A partir de aquí, todos los comandos se ejecutan dentro del servidor.

---

### Paso 4 — Actualizar el sistema e instalar herramientas base

```bash
sudo dnf update -y
sudo dnf install -y tmux git
```

---

### Paso 5 — Instalar uv (gestor de paquetes de Python)

`uv` se encarga de instalar Python y todas las dependencias del proyecto automáticamente.

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env
```

Verificar instalación:

```bash
uv --version
```

---

### Paso 6 — Instalar Python 3.12

```bash
uv python install 3.12
```

---

### Paso 7 — Clonar el repositorio

```bash
git clone https://github.com/DiegoPyLL/CarFlip
cd CarFlip
```

---

### Paso 8 — Instalar las dependencias del proyecto

```bash
uv sync
```

Esto crea el entorno virtual `.venv` e instala todo automáticamente.

---

### Paso 9 — Instalar el navegador para Playwright

Playwright necesita un navegador (Chromium) para acceder a sitios con JavaScript como Yapo:

```bash
uv run playwright install chromium
```

---

### Paso 10 — Crear el archivo de configuración `.env`

Este archivo contiene las credenciales y ajustes del sistema. Nunca se sube al repositorio.

```bash
nano .env
```

Pega el siguiente contenido y reemplaza los valores con los tuyos:

```env
# Base de datos (URL de tu instancia PostgreSQL externa)
DATABASE_URL=postgresql+asyncpg://usuario:password@host:5432/carflip

# MercadoLibre API
MERCADOLIBRE_APP_ID=tu_app_id
MERCADOLIBRE_CLIENT_SECRET=tu_client_secret

# S3 — almacenamiento intermedio de fotos
S3_ACCESS_KEY_ID=tu_access_key
S3_SECRET_ACCESS_KEY=tu_secret_key
S3_REGION=us-east-1
S3_BUCKET=carflip-raw
S3_PREFIX=raw/

# Cloudflare R2 — CDN de imágenes
R2_ACCOUNT_ID=tu_account_id
R2_BUCKET=carflip-fotos
R2_ACCESS_KEY_ID=tu_r2_access_key
R2_SECRET_ACCESS_KEY=tu_r2_secret_key
R2_PREFIX=autocosmos/fotos/

# Velocidad de scraping (segundos entre requests)
MIN_DELAY_SECONDS=2.0
MAX_DELAY_SECONDS=6.0

# Frecuencia del scheduler
SCRAPE_INTERVAL_HOURS=6

# Detección de deals
DEAL_THRESHOLD_PCT=15.0

# Logs
LOG_LEVEL=INFO
LOG_FILE=logs/carflip.log
```

Para guardar y salir de nano: `Ctrl+O` → `Enter` → `Ctrl+X`

---

### Paso 11 — Crear las tablas en la base de datos

```bash
uv run alembic upgrade head
```

Si no hay errores, las tablas están listas.

---

### Paso 12 — Activar el entorno virtual

```bash
source .venv/bin/activate
```

El prompt cambiará y mostrará `(.venv)` al inicio. A partir de aquí puedes usar el comando `carflip` directamente.

---

### Paso 13 — Abrir una sesión tmux y ejecutar CarFlip

`tmux` permite que el programa siga corriendo aunque cierres la conexión SSH. Sin esto, el proceso se detiene al cerrar la terminal.

Crear una sesión nueva:

```bash
tmux new -s carflip
```

Dentro de la sesión, probar que todo funciona con una ejecución única:

```bash
carflip run
```

Si no hay errores, iniciar el scheduler automático:

```bash
carflip start
```

Desconectarse sin detener el proceso (el programa sigue corriendo en el servidor):

```
Ctrl+B  →  D
```

Para volver a ver los logs en cualquier momento:

```bash
tmux attach -t carflip
```

---

## Comandos disponibles

| Comando | Descripción |
|---|---|
| `carflip run` | Ejecuta todos los scrapers una sola vez |
| `carflip run --scraper autocosmos` | Ejecuta solo un scraper específico |
| `carflip start` | Inicia el scheduler automático (cada `SCRAPE_INTERVAL_HOURS` horas) |
| `carflip market Toyota Corolla 2020` | Estadísticas de mercado para un modelo |

---

## Comandos de tmux útiles

| Comando | Descripción |
|---|---|
| `tmux new -s carflip` | Crear sesión nueva |
| `tmux attach -t carflip` | Volver a la sesión existente |
| `tmux ls` | Ver todas las sesiones activas |
| `Ctrl+B  D` | Desconectarse sin detener el proceso |
| `Ctrl+B  [` | Scroll para ver logs anteriores (`Q` para salir) |

---

## Resolución de problemas

### "command not found: carflip" al reconectar SSH

El entorno virtual no se mantiene entre sesiones. Hay que activarlo de nuevo o usar la ruta directa:

```bash
# Opción 1: activar el venv
source .venv/bin/activate
carflip start

# Opción 2: ruta directa (sin activar)
.venv/bin/carflip start
```

### Timeouts o errores en Yapo (Playwright)

Aumentar los delays en `.env`:

```env
MIN_DELAY_SECONDS=3.0
MAX_DELAY_SECONDS=8.0
```

---

## Documentación técnica

- [CLAUDE.md](CLAUDE.md) — Arquitectura, convenciones y decisiones de diseño
- [CHANGELOG.md](CHANGELOG.md) — Historial de versiones

---

**CarFlip — Inteligencia de Mercado Automotriz**
