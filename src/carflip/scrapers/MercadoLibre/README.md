# STANDBY

# MercadoLibre API Client

Cliente asincrónico HTTP para la API oficial de MercadoLibre Chile. Obtiene avisos de autos y motos con paginación automática y rate limiting.

**Ubicación del módulo:** `c:\Users\Laptop\Desktop\Trabajos\ProyectosPersonales\CarFlip\src\carflip\scrapers\MercadoLibre\`

## Instalación de dependencias

### Opción 1: Desde el proyecto principal (recomendado)

Si estás usando el proyecto CarFlip completo, las dependencias ya están instaladas con:

```bash
cd c:\Users\Laptop\Desktop\Trabajos\ProyectosPersonales\CarFlip
uv sync
```

### Opción 2: Dependencias locales (carpeta aislada) — RECOMENDADO PARA ESTE MÓDULO

Si quieres instalar solo para el módulo MercadoLibre con ruta directa:

```bash
# Con pip — ruta directa al requirements.txt
pip install -r "c:\Users\Laptop\Desktop\Trabajos\ProyectosPersonales\CarFlip\src\carflip\scrapers\MercadoLibre\requirements.txt"

# O con uv (más rápido) — ruta directa
uv pip install -r "c:\Users\Laptop\Desktop\Trabajos\ProyectosPersonales\CarFlip\src\carflip\scrapers\MercadoLibre\requirements.txt"

# O navegar a la carpeta primero
cd "src\carflip\scrapers\MercadoLibre"
pip install -r requirements.txt
```

⚠️ **NOTA:** El archivo `requirements.txt` de este módulo está específicamente en:

```
c:\Users\Laptop\Desktop\Trabajos\ProyectosPersonales\CarFlip\src\carflip\scrapers\MercadoLibre\requirements.txt
```

**NO confundir con otros `requirements.txt` que puedan existir en el proyecto.**

## Dependencias

| Paquete               | Versión | Propósito                   |
| --------------------- | -------- | ---------------------------- |
| `httpx`             | ≥0.27   | Cliente HTTP asincrónico    |
| `fake-useragent`    | ≥1.5    | User-Agent rotativo anti-bot |
| `loguru`            | ≥0.7    | Logging estructurado         |
| `pydantic`          | ≥2.7    | Validación de datos         |
| `pydantic-settings` | ≥2.3    | Gestión de configuración   |

## Uso

### Desde el CLI del proyecto (recomendado)

```bash
cd c:\Users\Laptop\Desktop\Trabajos\ProyectosPersonales\CarFlip
carflipper fetch --max 50
```

### Desde Python (uso directo)

```python
from carflip.scrapers.mercadolibre import MercadoLibreClient

async def main():
    async with MercadoLibreClient() as client:
        # Obtener autos y motos
        resultados = await client.fetch_todo(max_por_categoria=50)
    
        autos = resultados["autos"]  # list[AvisoAuto]
        motos = resultados["motos"]  # list[AvisoAuto]
    
        for aviso in autos:
            print(f"{aviso.titulo} - ${aviso.precio} {aviso.moneda}")

# Ejecutar
import asyncio
asyncio.run(main())
```

### Script de ejemplo independiente

```bash
# Navegar al módulo
cd "c:\Users\Laptop\Desktop\Trabajos\ProyectosPersonales\CarFlip\src\carflip\scrapers\MercadoLibre"

# Instalar dependencias (solo primera vez)
pip install -r requirements.txt

# Ejecutar el ejemplo
python example.py --max 50
```

## Configuración

Las variables de entorno se pueden definir en `.env`:

```env
MIN_DELAY_SECONDS=2.0          # Delay mínimo entre requests
MAX_DELAY_SECONDS=6.0          # Delay máximo entre requests
MERCADOLIBRE_APP_ID=           # (Opcional) ID de app para mayor rate limit
MERCADOLIBRE_CLIENT_SECRET=    # (Opcional) Secret de la app
```

## Rate Limiting

El cliente respeta automáticamente un delay aleatorio entre requests:

- **Rango default**: 2-6 segundos
- **Configurable** en `settings.min_delay_seconds` y `settings.max_delay_seconds`
- **Automático** entre cada página de paginación (máx 50 resultados por request)

## Estructura de datos

Cada aviso se mapea a un objeto `AvisoAuto`:

```python
@dataclass
class AvisoAuto:
    fuente: str                          # "mercadolibre"
    id_externo: str                      # ID único en ML
    url: str                             # Enlace directo al aviso
    titulo: str                          # Descripción completa
    precio: Decimal | None               # En pesos
    moneda: str                          # Moneda (default "CLP")
    marca: str | None                    # Toyota, Honda, etc.
    modelo: str | None                   # Corolla, Civic, etc.
    anio: int | None                     # Año de fabricación
    km: int | None                       # Kilometraje
    ubicacion: str | None                # Región o ciudad
    combustible: str | None              # Bencina, Diesel, Híbrido, etc.
    descripcion: str | None              # (vacío en API pública)
    url_imagen: str | None               # Thumbnail
    disponible: bool | None              # True si está activo
    fecha_publicacion: str | None        # (vacío en API pública)
```

## CLI Integration

Si estás usando CarFlip, usa el comando integrado:

```bash
carflipper fetch --max 100
```

Genera archivos Markdown en: `C:\...\CarFlip\Archivos locales\`

## Testing

```bash
cd "c:\Users\Laptop\Desktop\Trabajos\ProyectosPersonales\CarFlip"
pytest tests/test_mercadolibre.py -v
```

## 📋 Quick Reference

| Tarea                                          | Comando                                                                                                                              |
| ---------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| **Instalar dependencias (ruta directa)** | `pip install -r "c:\Users\Laptop\Desktop\Trabajos\ProyectosPersonales\CarFlip\src\carflip\scrapers\MercadoLibre\requirements.txt"` |
| **Ejecutar desde CLI**                   | `carflipper fetch --max 50`                                                                                                        |
| **Ejecutar script de ejemplo**           | `python "c:\Users\Laptop\Desktop\Trabajos\ProyectosPersonales\CarFlip\src\carflip\scrapers\MercadoLibre\example.py" --max 50`      |
| **Ver logs**                             | `c:\Users\Laptop\Desktop\Trabajos\ProyectosPersonales\CarFlip\logs\carflipper.log`                                                 |
| **Output Markdown**                      | `c:\Users\Laptop\Desktop\Trabajos\Duoc\3er Anio\1er Semestre\Gestion De Datos IA\CarFlip\Archivos locales\`                        |

## 📂 Archivos del módulo

```
c:\Users\Laptop\Desktop\Trabajos\ProyectosPersonales\CarFlip\
└── src\carflip\scrapers\MercadoLibre\
    ├── mercadolibre.py          ← Cliente HTTP principal
    ├── __init__.py              ← Inicializador del módulo
    ├── requirements.txt         ← ⭐ Dependencias (RUTA DIRECTA PARA INSTALAR)
    ├── README.md                ← Este archivo
    └── example.py               ← Script de ejemplo ejecutable
```

## Notas

- La API de MercadoLibre es **pública** — no requiere autenticación para búsquedas básicas.
- Con `app_id` configurado, obtienes límites de rate más altos.
- Cada request devuelve máximo 50 resultados; la paginación es automática.
- User-Agent se rota en cada request para evitar bloqueos.
- **Este módulo es autocontenido** — tiene sus propias dependencias en `requirements.txt`
