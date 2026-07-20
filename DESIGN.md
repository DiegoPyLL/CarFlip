# CarFlip — Referencia visual

> Galería acromática con escarlata racionado: fondo plano, tipografía en peso whisper, cero radio, y un solo punto rojo que marca la acción principal.

**Temas:** claro (principal) y oscuro (`:root[data-theme="dark"]`).

CarFlip es una plataforma de comparación de avisos de autos usados en Chile. El sistema visual trata cada listado como una pared de galería: la foto llega hasta el borde de la card, la separación se resuelve con líneas de 1px y espacio negativo, y la jerarquía la construye la tipografía —no el color ni la elevación—. El escarlata (`#e4002b`) funciona como puntuación, no como decoración: aparece una vez por pantalla, en el punto del CTA primario, en el borde de foco, o en el indicador de filtros activos. Todo lo demás es acromático, incluidas las señales que en otros productos serían verde/rojo (variaciones de precio, categorías de deal).

La densidad es la de un producto, no la de un portafolio: los saltos de 120px se reservan para páginas de marketing; los grids de resultados usan 16px.

---

## Tokens — Color

Los nombres son **semánticos**, no cromáticos: el mismo token cambia de valor según el tema. Nunca escribir un hex en un componente; siempre la utilidad Tailwind del token.

| Token             | Utilidad Tailwind | Claro     | Oscuro    | Rol                                                             |
| ----------------- | ----------------- | --------- | --------- | --------------------------------------------------------------- |
| `--c-canvas`      | `canvas`          | `#ffffff` | `#000000` | Fondo de página, header, footer, relleno de badges sobre imagen |
| `--c-surface`     | `surface`         | `#f4f4f4` | `#101010` | Placeholder de imagen, hover de filas, elevación mínima         |
| `--c-ink`         | `ink`             | `#000000` | `#ffffff` | Texto primario, títulos, precios, bordes en hover y estado activo |
| `--c-muted`       | `muted`           | `#5f5f5f` | `#a0a0a0` | Texto secundario, metadatos, labels, nav inactiva                |
| `--c-line`        | `line`            | `#dcdcdc` | `#484848` | Bordes de card, divisores, paginación deshabilitada             |
| `--c-line-strong` | `line-strong`     | `#767676` | `#a0a0a0` | Bordes de inputs y selects (necesitan 3:1 de contraste)         |
| `--c-scarlet`     | `scarlet-signal`  | `#e4002b` | `#e4002b` | Punto del CTA primario, borde de foco, indicador de filtros activos |

**Contraste verificado sobre su propio canvas:**

| Tema   | ink   | muted  | line-strong | scarlet |
| ------ | ----- | ------ | ----------- | ------- |
| claro  | 21:1  | 6.39:1 | 4.54:1      | 4.85:1  |
| oscuro | 21:1  | 8.03:1 | 8.03:1      | 4.33:1  |

El escarlata solo alcanza AA de texto normal en tema claro. En oscuro queda restringido a elementos gráficos (el cuadrado de 6px, el borde de foco) y nunca a texto de párrafo.

### Cambio de tema

El tema se aplica con `data-theme="dark"` en `<html>` y se persiste en `localStorage` bajo la clave `tema` (`'claro' | 'oscuro'`). Un script inline y bloqueante en `<head>` lo aplica antes del primer pintado para evitar el flash. La variante `dark:` de Tailwind está redefinida con `@custom-variant` para seguir el atributo, no el media query del sistema: manda la preferencia guardada.

---

## Tokens — Tipografía

**Sin webfonts.** Se usa el stack de sistema por defecto de Tailwind (`ui-sans-serif, system-ui, …`). Es una decisión de rendimiento: cero requests de fuente, cero FOUT, cero peso en el critical path. No introducir `@font-face` sin una razón que justifique el costo en Core Web Vitals.

**Pesos:** solo 300 y 400. El `body` es 300 por defecto y `h1/h2/h3` también: el peso whisper es la firma del sistema. No usar 600+.

**Tracking:** se aprieta a medida que crece el tamaño — `-0.01em` en body, `-0.02em` en títulos. Ambos son globales en `global.css`; no repetirlos por elemento.

### Escala en uso

| Rol                          | Utilidad                | Tamaño        | Dónde                                                      |
| ---------------------------- | ----------------------- | ------------- | ---------------------------------------------------------- |
| Label / badge                | `text-sm`               | 14px          | Labels de filtro (`uppercase tracking-wider`), fuente, riesgos |
| Body / nav / meta            | `text-base`             | 16px          | Casi todo: copy, nav, metadatos, botones, paginación       |
| Precio de card / h2          | `text-2xl`              | 24px          | Precio en `CardAviso`/`CardDeal`, títulos de sección       |
| Métrica interna              | `text-3xl` / `text-4xl` | 30 / 36px     | Solo `/dashboard`                                          |
| H1 de página / cifra hero    | `text-5xl sm:text-7xl`  | 48 → 72px     | H1 de cada página y la cifra de portada, con `leading-none` |

Los números siempre con `tabular-nums`: precios, kilometrajes, porcentajes y contadores no deben bailar entre filas.

---

## Tokens — Espaciado y forma

El ritmo vertical está adaptado al producto. Los 120/240px de portafolio hundirían un grid de 24 avisos bajo el fold, así que `editorial` se reserva a páginas de marketing (`/`, `/como-funciona`).

| Token                 | Utilidad     | Valor | Uso                                                          |
| --------------------- | ------------ | ----- | ------------------------------------------------------------ |
| `--spacing-element`   | `*-element`  | 16px  | Gutter de grids, padding de cards, gaps internos              |
| `--spacing-block`     | `*-block`    | 48px  | Separación entre bloques dentro de una sección, padding de `<main>` en desktop |
| `--spacing-section`   | `*-section`  | 80px  | Separación entre secciones, margen superior del footer y de la paginación |
| `--spacing-editorial` | `*-editorial`| 120px | Respiro máximo entre secciones, solo en páginas editoriales (`lg:` en adelante) |

### Radio

**Todos los radios son 0px**, incluidas todas las variantes de Tailwind (`--radius-xs` … `--radius-4xl`). Si sobrevive algún `rounded-*` en el código queda inerte por construcción. No reintroducir esquinas redondeadas.

---

## Layout

- Contenedor único: `max-w-7xl mx-auto px-4 sm:px-6 lg:px-8`. Header, `main` y footer comparten el mismo, así que todo se alinea a la misma columna.
- `<body>`: `flex flex-col min-h-screen`, `main` con `flex-1` — el footer queda abajo aunque la página sea corta.
- Header: `sticky top-0 z-20`, altura fija de 48px (`h-12`), fondo `canvas` sin borde ni blur. La barra se funde con el canvas.
- `main`: `py-8 lg:py-block`.
- Grid de resultados: `grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-element`. En `/avisos` convive con un sidebar de `lg:w-48` sticky.

### Breakpoints

| | S | M | L | XL |
|-|---|---|---|----|
| Tailwind | base | `sm:` 640px | `lg:` 1024px | `xl:` 1280px+ |
| Qué cambia | 1 columna, sidebar colapsado tras un toggle, nav reducida | 2 columnas, tipografía hero a 72px | 3 columnas, sidebar visible, `lg:py-block`, saltos `editorial` | Solo más aire lateral; el contenido tope en `max-w-7xl` |

A 320px no caben cinco enlaces de nav más el logo y el toggle. Se ocultan por orden de redundancia: `Home` (el logo ya lleva ahí) y `Cómo funciona` (la sección menos transaccional). Ninguna queda inalcanzable.

---

## Estructura del sitio

| Ruta               | Rol                                                                       |
| ------------------ | ------------------------------------------------------------------------- |
| `/`                | Portada: hero + CTA, cifra de portada con pares label/valor, últimos avisos, lista "Explorar". Con querystring redirige 301 a `/avisos` (preserva backlinks del listado antiguo) |
| `/avisos`          | Listado completo: `FiltrosBarra` + `FiltrosSidebar` + grid de `CardAviso` + `Paginacion` |
| `/auto/[id]`       | Detalle del aviso; recibe `?back=` para volver al listado con sus filtros  |
| `/deals`           | Autos bajo precio de mercado, evaluados por IA: grid de `CardDeal`         |
| `/mercado`         | Precios promedio, marcas y modelos más listados                           |
| `/marcas/[marca]`  | Corte de mercado por marca                                                |
| `/como-funciona`   | Página editorial: de dónde salen los datos y cómo se detectan oportunidades |
| `/dashboard`       | Métricas operacionales internas                                           |

---

## Componentes

### Header

Tres zonas en 48px de alto: izquierda, wordmark `CarFlip` en `text-base font-normal text-ink` seguido del descriptor "Comparador de autos Chile" en `muted` (solo `lg:`); derecha, la nav y el toggle de tema. Enlaces en `text-base`, `muted` en reposo y `ink` con `underline underline-offset-4` cuando están activos. `/` solo marca activo en coincidencia exacta; el resto también en sus subrutas (`/marcas/Kia` resalta Mercado, `/auto/814` resalta Avisos), vía `aria-current="page"`.

### Toggle de tema

Botón de 40×40 (target táctil) con dos SVG inline —luna y sol— que se alternan con `dark:hidden` / `hidden dark:block`. El `aria-label` se reetiqueta por JS al estado destino ("Cambiar a tema oscuro" / "claro").

### CardAviso

`<article>` con `border border-line`, hover a `border-ink` en 200ms. Sin radio, sin sombra, sin transform. La imagen es `aspect-[4/3] object-cover` sobre `bg-surface`; su borde ES el borde de la card. Badges absolutos arriba a la izquierda sobre `bg-canvas/75`: fuente, variación de precio y, si aplica, "No disponible" tachado. Cuerpo con `p-element`: título en `text-base text-muted line-clamp-2`, precio en `text-2xl text-ink tabular-nums`, y metadatos (`año · km · ubicación`) unidos con ` · ` en una sola línea con `truncate`.

### CardDeal

Misma anatomía, imagen `aspect-[16/10]`. La diferencia es el badge de categoría IA arriba a la derecha, que **jerarquiza por relleno y borde, no por color**:

| Categoría           | Estilo                              |
| ------------------- | ----------------------------------- |
| `oportunidad_clara` | `bg-ink text-canvas`                |
| `buen_precio`       | `bg-canvas text-ink border-ink`     |
| `revisar`           | `bg-canvas text-muted border-muted` |
| `descartar`         | `bg-canvas text-muted border-line`  |
| `sin_evaluar`       | `bg-canvas text-muted border-line`  |

La etiqueta de texto siempre acompaña, así que no se pierde información sin el color. Debajo del precio conviven el puntaje IA (`n/100`), el % vs mercado, la bajada propia del aviso, hasta 3 chips de riesgo con `+n` de overflow, y el resumen de la IA en `line-clamp-2`.

### Señales de variación de precio

`signosDelta()` devuelve glifo + token, nunca verde ni rojo: bajada → `▼ n%` en `text-ink` (gana peso porque es la buena noticia), alza → `▲ n%` en `text-muted`. El glifo carga el significado; el color solo el énfasis.

### FiltrosBarra

Bloque sobre el listado, cerrado con `border-b border-line`. Fuente como `fieldset` de radios ocultos (`sr-only peer`) con etiquetas tipo toggle: `border-line-strong text-muted` en reposo, `peer-checked:bg-ink peer-checked:text-canvas`. Debajo, selects de marca y año, más las acciones a la derecha: "Filtrar" con borde `ink` y el cuadrado escarlata de 6px, y "Limpiar" como enlace `muted`. A anchos chicos se apila en dos bloques.

### FiltrosSidebar

`aside` de `lg:w-48`, `lg:sticky lg:top-20`. En mobile está oculto tras un botón toggle que anuncia "Filtros avanzados activos" con un cuadrado escarlata cuando hay alguno aplicado. Un único set de inputs para no duplicar campos al enviar el form. Inputs y selects: `bg-canvas border border-line-strong px-3 py-2`, foco con `focus:outline-hidden focus:border-scarlet-signal`.

### Paginacion

Solo se renderiza con más de una página. Ventana de ±2 alrededor de la actual, con `1 … n` en los extremos. Página actual en `bg-ink text-canvas`; el resto `muted → ink` en hover; deshabilitados en `text-line` con `aria-disabled`. Pagina sobre `Astro.url.pathname`, así que sirve en cualquier listado.

### Lista "Explorar"

Filas apiladas con `divide-y divide-line border-y border-line`, sin cajas. Cada fila: título en `text-2xl text-ink` con ancho fijo, detalle en `muted`, flecha `→` a la derecha, hover a `bg-surface`. Prueba de que el texto apilado estructura mejor que una grilla de tarjetas.

### Bloque de cifras

Pares label/valor sin bordes ni cajas: label en `text-base text-muted`, valor justo debajo en `text-base text-ink tabular-nums`. Se distribuyen con `flex flex-wrap gap-x-block gap-y-element`. La tipografía hace el trabajo de estructurar.

### CTA primario

`inline-flex` con borde `ink`, `px-6 py-3`, hover que invierte a `bg-ink text-canvas`. Lo precede un cuadrado de 6px en `bg-scarlet-signal` marcado `aria-hidden`. Es el único botón con presencia; el resto de acciones son enlaces o botones con borde.

### Footer

`border-t border-line`, `mt-section`, `py-element`. Wordmark en `ink`, copyright y descriptor en `muted`. Sin CTAs.

---

## Elevación

No hay elevación. El sistema separa con vacío y con líneas de 1px, nunca con sombra, glow ni lift tonal. Las cards viven en el mismo plano que la página y se distinguen solo por su contenido y su borde. `surface` existe para placeholders y hovers, no para simular altura.

---

## Imágenes

Las fotos vienen de los portales de origen vía CDN, resueltas por `resolverUrlImagen()`. Reglas:

- `object-cover` en un contenedor con `aspect-ratio` fijo — la caja nunca depende de la imagen, así no hay layout shift.
- `width`/`height` explícitos y `loading="lazy"` en todas las de listado.
- Sin radio, sin padding interno, sin overlays decorativos. Los únicos elementos encima son los badges, sobre `bg-canvas/75`.
- Fallback siempre presente: "Sin imagen" centrado en `bg-surface` con el mismo aspect-ratio.
- `alt` = título del aviso.

---

## Racionamiento del color

El sistema opera con una ración estricta: ~95% acromático, ~5% escarlata. Como máximo un elemento escarlata por pantalla. Cuando varios elementos compiten por atención, la respuesta es más espacio negativo, tipografía más chica o peso más liviano — nunca más color.

Los tres usos legítimos del escarlata son:

1. El cuadrado de 6px del CTA primario.
2. El borde de foco de inputs, selects y botones.
3. El indicador de "filtros avanzados activos".

---

## Do's

- Usar siempre los tokens semánticos (`canvas`, `ink`, `muted`, `line`, `line-strong`, `surface`); nunca un hex ni un `gray-*` de Tailwind.
- Verificar cada cambio en **ambos temas**: un color que funciona en claro puede quedar bajo AA en oscuro.
- Mantener todos los radios en 0.
- Usar `tabular-nums` en cualquier número que se repita entre filas.
- Codificar el significado en texto o glifo primero, y usar el color solo como énfasis.
- Usar `element` para densidad, `block`/`section` para respiro de producto, y `editorial` solo en páginas de marketing.
- Bordes de inputs con `line-strong` (3:1); `line` es demasiado sutil para un control interactivo.
- Dar a los targets táctiles al menos 40px de alto.

## Don'ts

- No introducir verde ni rojo semántico. Las bajadas de precio, las buenas oportunidades y los riesgos se resuelven con glifo, peso y relleno acromático.
- No agregar un segundo color de acento. El escarlata es la única señal cromática del sistema.
- No usar sombras, glows ni gradientes en elementos de UI.
- No usar pesos 600+.
- No agregar webfonts sin justificar el costo en Core Web Vitals.
- No usar `dark:` esperando el media query del sistema: la variante está redefinida sobre `data-theme`.
- No centrar párrafos largos; toda copia extensa se alinea a la izquierda.
- No dejar que el escarlata cargue significado por sí solo — para daltonismo y modo oscuro, siempre debe haber texto o forma que lo respalde.
- No trasladar el ritmo de 120/240px a los listados: hunde los resultados bajo el fold.

---

## Referencia rápida

```
texto primario      → text-ink
texto secundario    → text-muted
fondo               → bg-canvas
superficie/hover    → bg-surface
borde/divisor       → border-line
borde de control    → border-line-strong
acento (escaso)     → bg-scarlet-signal / focus:border-scarlet-signal
radio               → 0
peso                → 300 (400 solo para el wordmark)
gutter de grid      → gap-element (16px)
salto de sección    → mb-section (80px) · mb-editorial (120px) solo en marketing
```

Los tokens se definen en [global.css](web/src/styles/global.css) y se consumen exclusivamente vía utilidades de Tailwind v4.
