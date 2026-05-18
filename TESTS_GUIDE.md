# Guía de Tests — Etapa 1 (Ingesta)

## Descripción

Los tests validan que los scrapers **ejecuten correctamente** y generen datos en `data/raw/`:

- `test_yapo_cloud_ingesta.py` — Tests para `ScraperYapoCloud` (yapoCloud.py)
- `test_autocosmos_cloud_ingesta.py` — Tests para `ScraperAutocosmosCloud` (autocosmosCloud.py)

**No requieren conexión a Internet** porque mockean las respuestas HTTP/Playwright.

---

## Instalación de dependencias

```bash
uv sync
```

Asegúrate de tener `pytest-asyncio` en las dev dependencies (ya está en `pyproject.toml`).

---

## Ejecutar todos los tests

```bash
pytest tests/
```

## Ejecutar tests específicos

**Solo Autocosmos:**
```bash
pytest tests/test_autocosmos_cloud_ingesta.py -v
```

**Solo Yapo:**
```bash
pytest tests/test_yapo_cloud_ingesta.py -v
```

**Un test específico:**
```bash
pytest tests/test_autocosmos_cloud_ingesta.py::TestParsersAutocosmosCloud::test_parsear_precio_clp_formateado -v
```

---

## Interpretar resultados

### Test pasa ✓
```
test_parsear_precio_clp_formateado PASSED [100%]
```

### Test falla ✗
```
test_parsear_precio_clp_formateado FAILED [100%]
AssertionError: assert None == Decimal('8500000')
```

---

## Cobertura de tests

### AutocosmosCloud (`test_autocosmos_cloud_ingesta.py`)

**Parsers puros** (sin I/O):
- ✓ `_parsear_precio()` — 3 casos: formateado, sin separadores, inválido
- ✓ `_parsear_km()` — 3 casos: formateado, sin separadores, inválido
- ✓ `_parsear_anio()` — 2 casos: válido, no encontrado
- ✓ `_parsear_ubicacion()` — 2 casos: con pipe, sin ubicación

**Validación**:
- ✓ Aviso válido pasa
- ✓ Precio bajo rechazado
- ✓ Precio alto rechazado
- ✓ Año fuera de rango rechazado
- ✓ Fecha futura rechazada
- ✓ KM negativo rechazado

**Extracción HTML**:
- ✓ `_extraer_cards()` — múltiples avisos, deduplicación
- ✓ `_parsear_aviso()` — desde tag HTML

**Integración**:
- ✓ `scrape()` retorna lista de avisos
- ✓ `scrape()` deduplica localmente
- ✓ `scrape()` rechaza avisos inválidos

### YapoCloud (`test_yapo_cloud_ingesta.py`)

**Métodos puros**:
- ✓ `_limpiar_km()` — parsing de km
- ✓ `_limpiar_precio()` — parsing de precio
- ✓ `_normalizar_combustible()` — tipos de combustible
- ✓ `_get_attr()` — búsqueda de atributos con normalización Unicode

**Integración**:
- ✓ `scrape()` retorna lista de avisos
- ✓ Avisos tienen campos requeridos
- ✓ Avisos pasan validación

---

## ¿Qué mockean estos tests?

### Autocosmos (httpx)
```python
# Mock httpx.AsyncClient.get() para evitar llamadas HTTP reales
mock_client.get = AsyncMock(return_value=mock_response)
```

### Yapo (Playwright)
```python
# Mock async_playwright context manager
# Mock browser, context, page, querySelectorAll, evaluate, etc.
```

---

## Próximos pasos (Etapas 2-4)

Cuando llegues a:
- **Etapa 2 (Limpieza)**: agrega tests para `pipeline_limpiar.py`
- **Etapa 3 (Validación)**: agrega tests para `pipeline_validar.py`
- **Etapa 4 (Carga)**: agrega tests para `pipeline_cargar.py`

---

## Troubleshooting

### `ModuleNotFoundError: No module named 'carflip'`
Asegúrate de que estás en el directorio correcto y has ejecutado `uv sync`:
```bash
cd /path/to/CarFlip
uv sync
```

### `asyncio.InvalidStateError`
Asegúrate de tener `pytest-asyncio >= 0.21` en dev dependencies (ya está incluido).

### Los tests de Yapo usan mucha memoria
Los mocks de Playwright son complejos. Esto es normal. Puedes ejecutar tests en secuencia con `-n0`:
```bash
pytest tests/test_yapo_cloud_ingesta.py -n0
```
