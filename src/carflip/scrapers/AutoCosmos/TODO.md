# TODO — Scraper AutoCosmos

Problemas identificados en la revisión de código de `autocosmos.py`. Ordenados por severidad.

---

## Media — afectan robustez o mantenibilidad

### [ ] Eliminar duplicación del loop de paginación

`fetch_usados()` y `fetch_todo()` tienen el mismo loop copiado. La única diferencia es que
`fetch_todo` descarga imágenes y escribe `.md` inline.

**Solución sugerida:** extraer `_paginar()` como generador async que emita `(pagina, cards)` y
que ambos métodos consuman. Así cualquier cambio en paginación (retry, detección de última
página) aplica a los dos.

---

### [ ] Agregar retry con backoff ante errores de red

Cualquier excepción en `_hacer_request()` ejecuta `break` y descarta todas las páginas
restantes. Un error transitorio en la página 50 de 200 termina el scrape silenciosamente con
datos parciales.

**Solución sugerida:** envolver la llamada en un loop de reintento (máximo 3 intentos, backoff
exponencial 2s→4s→8s) antes de hacer `break`. Loggear `logger.warning` en cada reintento y
`logger.error` al agotar intentos.

---

### [ ] Distinguir fin real de página vs. página de error con HTTP 200

La condición `if not cards: break` termina la paginación en dos casos distintos:
- El sitio devolvió la última página vacía (correcto).
- El sitio devolvió una página de error con código 200 que no tiene cards (falso fin).

**Solución sugerida:** verificar también si el HTML contiene algún indicador de "no hay
resultados" del sitio (buscar un selector específico o un texto conocido) para distinguir entre
los dos casos.

---

## Baja — mejoras de calidad o completitud de datos

### [ ] Extraer versión/trim del URL

El patrón de URL es `/auto/usado/{marca}/{modelo}/{version}/{id}`. La versión (e.g., `2-0-xei`,
`sport-4x4`) está disponible en `partes[5]` pero se descarta. Es un campo valioso para
comparaciones de mercado.

**Acción:** agregar `version` a `AvisoAuto` y extraerla en `_parsear_aviso()`.

---

### [ ] Centralizar el delay en `espera_aleatoria()` de ScraperBase

`AutocosmosClient` llama `asyncio.sleep(random.uniform(...))` inline en el loop porque no es
un `ScraperBase` y no puede llamar `self.espera_aleatoria()`. Si la lógica del delay cambia
en `ScraperBase`, el cliente no lo hereda.

**Solución sugerida:** pasar `espera_aleatoria` como callable al cliente, o mover el delay al
`ScraperAutocosmos.scrape()` entre iteraciones en lugar de dentro del cliente.

---

### [ ] `fetch_todo` y `_construir_markdown_aviso` son código muerto en producción

`ScraperAutocosmos.scrape()` solo llama a `fetch_usados()`. El pipeline de guardado de
imágenes y Markdown solo se activa desde el bloque `__main__`. En el runner y el scheduler
nunca se ejecuta.

**Opciones:**
- Mover `fetch_todo` y `_construir_markdown_aviso` a un script separado `export.py` dentro
  de esta carpeta, para dejar claro que es una utilidad de desarrollo.
- O eliminarlo si no se planea mantener la exportación a Markdown.

---

### [ ] `__main__` reimplementa `ScraperBase.ejecutar()`

El bloque `__main__` hace el upsert directamente con `upsert_avisos()` y abre su propia
sesión. Esto duplica lo que `ejecutar()` ya hace. Si `ejecutar()` agrega lógica (e.g., escribir
en `ScrapedRun`), el `__main__` queda desactualizado.

**Solución sugerida:** reemplazar el bloque por:
```python
async with AsyncSessionLocal() as session:
    resultado = await ScraperAutocosmos(max_paginas=max_paginas).ejecutar(session)
logger.info(f"Avisos subidos: {len(resultado.avisos)}")
```

---

## Cosmética / type safety

### [ ] Cast explícito de `url_imagen` a `str`

```python
url_imagen = img.get("src") or img.get("data-src")
```

`BeautifulSoup.Tag.get()` devuelve `str | list[str] | None`. Para `src` casi siempre es
`str`, pero no hay garantía. Agregar `str(url_imagen) if url_imagen else None`.

---

### [ ] Comentar el `# type: ignore[override]` en `model_class`

```python
@property
def model_class(self) -> type:  # type: ignore[override]
```

El ignore suprime el error de mypy al sobrescribir un atributo de clase con un `@property`.
Agregar una línea explicando por qué (import diferido para evitar circular import en tiempo de
carga del módulo).

---

### [ ] Mutación implícita del set `vistos` en `_extraer_cards`

```python
def _extraer_cards(self, html: str, vistos: set[str] | None = None) -> list[Tag]:
    local: set[str] = vistos if vistos is not None else set()
    ...
    local.add(h)  # muta el set del llamador si vistos no es None
```

El nombre `local` es engañoso porque cuando `vistos` no es `None`, `local` apunta al mismo
objeto. Renombrar el parámetro a `dedup_set` o documentar explícitamente la mutación.

---

## Notas

- La lógica de upsert con detección de cambio de precio está en `uploader.py` y funciona
  correctamente — no requiere cambios.
- El patrón regex `_PATRON_AVISO` es robusto.
- La deduplicación de hrefs con el set `vistos` es correcta en su efecto, solo confusa en su
  implementación.
