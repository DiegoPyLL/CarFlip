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
| `--c-blue`        | `blue-signal`     | `#1873b3` | `#1873b3` | Acento editorial: fondo de bloques de marca (footer, `/quienes-somos`) |
| `--c-green`       | `green-signal`    | `#71db4c` | `#71db4c` | Acento editorial secundario, mismo régimen que `blue-signal`; reservado, sin implementación asignada |
| `--c-ink-on-tint` | `ink-on-tint`     | `#ffffff` | `#ffffff` | Blanco fijo para texto sobre `blue-signal`/`green-signal`; no invierte con el tema |
| `--c-github`      | `github-signal`   | `#181717` | `#181717` | Negro de marca de GitHub, solo para el ícono del footer; no es un acento del sistema |

**Contraste verificado sobre su propio canvas:**

| Tema   | ink   | muted  | line-strong | scarlet |
| ------ | ----- | ------ | ----------- | ------- |
| claro  | 21:1  | 6.39:1 | 4.54:1      | 4.85:1  |
| oscuro | 21:1  | 8.03:1 | 8.03:1      | 4.33:1  |

El escarlata solo alcanza AA de texto normal en tema claro. En oscuro queda restringido a elementos gráficos (el cuadrado de 6px, el borde de foco) y nunca a texto de párrafo.

### Acentos de fondo (`blue-signal` / `green-signal`)

`blue-signal` y `green-signal` solo se usan como **fondo de bloque** (footer, hero de `/quienes-somos`), nunca como color de texto sobre `canvas`, y el texto que va encima siempre es blanco (`ink-on-tint`), no `ink`: `ink` es negro en tema claro y perdería contraste sobre estos fondos.

| Fondo                              | Contraste con blanco |
| ----------------------------------- | --------------------- |
| `blue-signal` (`#1873b3`)           | 5.07:1 — pasa AA      |
| `green-signal` (`#71db4c`, sin implementar) | 1.76:1 — fallaría AA  |

`blue-signal` se profundizó a propósito desde el azul pedido originalmente (`#43a8ee`): ese tono solo daba 2.6:1 con blanco, bajo el 4.5:1 que exige AA. `#1873b3` conserva la misma familia de azul pero con luminancia suficiente para que el texto blanco cumpla. Si `green-signal` llega a implementarse con texto encima, necesita el mismo ajuste antes de usarse — el `#71db4c` documentado es el tono pedido, no uno ya verificado para texto.

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
| `/auto/[id]`       | Detalle del aviso recopilado; recibe `?back=` para volver al listado con sus filtros |
| `/auto/p/[id]`     | Detalle de un aviso de particular: galería, ficha y bloque de contacto. Admite sufijo de slug (`/auto/p/123-toyota-yaris-2018`), con canónica siempre a la forma corta |
| `/deals`           | Autos bajo precio de mercado, evaluados por IA: grid de `CardDeal`         |
| `/mercado`         | Precios promedio, marcas y modelos más listados                           |
| `/marcas/[marca]`  | Corte de mercado por marca                                                |
| `/como-funciona`   | Página editorial: de dónde salen los datos y cómo se detectan oportunidades, con FAQ ancladas en `#preguntas-frecuentes` |
| `/quienes-somos`   | Página editorial: la misión del equipo detrás de CarFlip                  |
| `/contacto`        | Página utilitaria: formulario de contacto (POST a `/api/contacto`, sin JS) |
| `/condiciones-de-uso` | Página utilitaria: términos de uso del sitio                           |
| `/privacidad`      | Página utilitaria: tratamiento de datos y analítica                       |
| `/legal`           | Página utilitaria: aviso legal (identificación, responsabilidad)          |
| `/entrar`, `/registro` | Páginas utilitarias de sesión, `noindex`. Un solo formulario sin JS con tres caminos: contraseña, enlace mágico y Google |
| `/cuenta`          | Página utilitaria `noindex`: datos de contacto, enlace a las publicaciones y eliminación de cuenta |
| `/cuenta/avisos`   | "Mis publicaciones": filas `divide-y` con estado y acciones en línea      |
| `/cuenta/avisos/nuevo`, `/cuenta/avisos/[id]/editar` | Formulario de publicación (`FormularioAviso` + `SubidorFotos`) |
| `/dashboard`       | Métricas operacionales internas y bandeja de moderación de reportes       |

---

## Componentes

### Header

Tres zonas en 48px de alto: izquierda, wordmark `CarFlip` en `text-base font-normal text-ink` seguido del descriptor "Comparador de autos Chile" en `muted` (solo `lg:`); derecha, la nav y el toggle de tema. Enlaces en `text-base`, `muted` en reposo y `ink` con `underline underline-offset-4` cuando están activos. `/` solo marca activo en coincidencia exacta; el resto también en sus subrutas (`/marcas/Kia` resalta Mercado, `/auto/814` resalta Avisos), vía `aria-current="page"`.

### Toggle de tema

Botón de 40×40 (target táctil) con dos SVG inline —luna y sol— que se alternan con `dark:hidden` / `hidden dark:block`. El `aria-label` se reetiqueta por JS al estado destino ("Cambiar a tema oscuro" / "claro").

### CardAviso

`<article>` con `border border-line`, hover a `border-ink` en 200ms. Sin radio, sin sombra, sin transform. La imagen es `aspect-[4/3] object-cover` sobre `bg-surface`; su borde ES el borde de la card. Badges absolutos arriba a la izquierda sobre `bg-canvas/75`: fuente, variación de precio y, si aplica, "No disponible" tachado. Cuerpo con `p-element`: título en `text-base  line-clamp-2`, precio en `text-2xl text-ink tabular-nums`, y metadatos (`año · km · ubicación`) unidos con ` · ` en una sola línea con `truncate`.

### CardDeal

Misma anatomía, imagen `aspect-[16/10]`. La diferencia es el badge de categoría IA arriba a la derecha, que **jerarquiza por relleno y borde, no por color**:

| Categoría           | Estilo                              |
| ------------------- | ----------------------------------- |
| `oportunidad_clara` | `bg-ink text-canvas`                |
| `buen_precio`       | `bg-canvas text-ink border-ink`     |
| `revisar`           | `bg-canvas  border-muted` |
| `descartar`         | `bg-canvas  border-line`  |
| `sin_evaluar`       | `bg-canvas  border-line`  |

La etiqueta de texto siempre acompaña, así que no se pierde información sin el color. Debajo del precio conviven el puntaje IA (`n/100`), el % vs mercado, la bajada propia del aviso, hasta 3 chips de riesgo con `+n` de overflow, y el resumen de la IA en `line-clamp-2`.

### Badge "Particular"

Los avisos publicados en el sitio llevan el mismo badge de fuente que los recopilados, con la etiqueta `Particular`, y comparten card, grid, filtros y señales de precio. La decisión de diseño es que **no se distinguen visualmente**: son una fuente más del listado, y darles un tratamiento propio sugeriría una jerarquía que el producto no tiene. Lo único distinto es el destino del enlace, que resuelve `enlaceAviso()`: `/auto/p/<id>` en vez de `/auto/<id>`.

### Galería del aviso de particular

Carrusel horizontal de `scroll-snap` (`snap-x snap-mandatory`) con las fotos a `aspect-[16/9] object-cover`, y miniaturas debajo que son `<a href="#foto-n">` sobre los `<li>` del carrusel. **Cero JavaScript y cero layout shift**: cada foto lleva `width`/`height` explícitos y la caja no depende de la imagen. La primera va `loading="eager"` + `fetchpriority="high"` + `decoding="sync"` porque es el LCP; el resto, `lazy`. El desplazamiento suave va tras `motion-safe:`.

### Bloque de contacto

Cierra el detalle de un aviso de particular, tras `border-t border-line`. Tiene tres estados y el servidor decide cuál pinta:

| Estado             | Qué se ve                                                                 |
| ------------------ | ------------------------------------------------------------------------- |
| Anónimo            | CTA que lleva a `/entrar?volver=…`. El teléfono no está en el HTML         |
| Con sesión         | CTA "Ver el teléfono del vendedor" (POST) y el aviso de que el vendedor verá el interés |
| Ya revelado        | Nombre en `text-2xl`, número en `text-3xl sm:text-5xl tabular-nums`, y los botones Llamar y WhatsApp |

El número escala recién en `sm:` porque sus 14 caracteres a `text-5xl` se salen de una pantalla de 320px. El teléfono nunca se renderiza oculto: si no corresponde mostrarlo, no llega al HTML — tampoco al JSON-LD, cuyo `seller` va sin nombre ni número.

### Señales de variación de precio

`signosDelta()` devuelve glifo + token, nunca verde ni rojo: bajada → `▼ n%` en `text-ink` (gana peso porque es la buena noticia), alza → `▲ n%` en ``. El glifo carga el significado; el color solo el énfasis.

### FiltrosBarra

Bloque sobre el listado, cerrado con `border-b border-line`. Fuente como `fieldset` de radios ocultos (`sr-only peer`) con etiquetas tipo toggle: `border-line-strong ` en reposo, `peer-checked:bg-ink peer-checked:text-canvas`. Debajo, selects de marca y año, más las acciones a la derecha: "Filtrar" con borde `ink` y el cuadrado escarlata de 6px, y "Limpiar" como enlace `muted`. A anchos chicos se apila en dos bloques.

### FiltrosSidebar

`aside` de `lg:w-48`, `lg:sticky lg:top-20`. En mobile está oculto tras un botón toggle que anuncia "Filtros avanzados activos" con un cuadrado escarlata cuando hay alguno aplicado. Un único set de inputs para no duplicar campos al enviar el form. Inputs y selects: `bg-canvas border border-line-strong px-3 py-2`, foco con `focus:outline-hidden focus:border-scarlet-signal`.

### Paginacion

Solo se renderiza con más de una página. Ventana de ±2 alrededor de la actual, con `1 … n` en los extremos. Página actual en `bg-ink text-canvas`; el resto `muted → ink` en hover; deshabilitados en `text-line` con `aria-disabled`. Pagina sobre `Astro.url.pathname`, así que sirve en cualquier listado.

### Lista "Explorar"

Filas apiladas con `divide-y divide-line border-y border-line`, sin cajas. Cada fila: título en `text-2xl text-ink` con ancho fijo, detalle en `muted`, flecha `→` a la derecha, hover a `bg-surface`. Prueba de que el texto apilado estructura mejor que una grilla de tarjetas.

### Bloque de cifras

Pares label/valor sin bordes ni cajas: label en `text-base `, valor justo debajo en `text-base text-ink tabular-nums`. Se distribuyen con `flex flex-wrap gap-x-block gap-y-element`. La tipografía hace el trabajo de estructurar.

### CTA primario

`inline-flex` con borde `ink`, `px-6 py-3`, hover que invierte a `bg-ink text-canvas`. Lo precede un cuadrado de 6px en `bg-scarlet-signal` marcado `aria-hidden`. Es el único botón con presencia; el resto de acciones son enlaces o botones con borde.

### Bandeja de reportes

Primera sección de `/dashboard`, anclada en `#reportes` y **fuera** del bloque de métricas: los reportes deben verse aunque no haya ninguna corrida de scraping registrada. Caja `border border-line` con cabecera, filas `divide-y divide-line` y las acciones en línea como enlaces subrayados, igual que en "Mis publicaciones" — despublicar es reversible (el autor puede republicar), así que no merece el peso visual de un botón. Los reportes ya revisados se pliegan en un `<details>` nativo, sin JS.

### Footer

`mt-section`, fondo `bg-blue-signal` (el único bloque del sitio con este acento). Todo el texto encima usa `ink-on-tint`, no `ink`. Tres zonas en `py-block`: wordmark + tagline + una línea de misión que enlaza a `/quienes-somos`; tres columnas de navegación (Producto: Avisos/Deals/Mercado; Compañía: Quiénes somos/Cómo funciona/Preguntas Frecuentes/Contáctanos/Github, con el ícono de Github inline en `github-signal` — el único color de marca ajeno al sistema, ver Tokens — Color; Legal: Condiciones de Uso/Términos de privacidad/Legales); barra inferior con `border-t border-ink-on-tint/15` y el copyright. Sin CTAs.

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

El sistema sigue siendo mayormente acromático. Hay tres acentos cromáticos y cada uno tiene un rol fijo — no son intercambiables ni conviven en una misma pantalla:

| Acento           | Rol                                                                       | Dónde                                                      |
| ---------------- | -------------------------------------------------------------------------- | ------------------------------------------------------------ |
| `scarlet-signal` | Transaccional: la única señal en las páginas de producto.                  | CTA primario, borde de foco, indicador de filtros activos    |
| `blue-signal`    | Editorial/institucional: identifica los bloques de marca, no de producto.  | Fondo del footer, hero de `/quienes-somos`                   |
| `green-signal`   | Editorial secundario, mismo régimen que `blue-signal`.                     | Reservado — sin implementación asignada todavía              |

Las páginas de producto (`/avisos`, `/deals`, `/mercado`, `/auto/[id]`, cards) mantienen la ración original: ~95% acromático, ~5% escarlata, un elemento como máximo por pantalla. `blue-signal`/`green-signal` no aparecen ahí — quedan reservados a los bloques editoriales/de marca.

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
- Usar `ink-on-tint` (no `ink`) para el texto sobre `blue-signal`/`green-signal`: `ink` es negro en tema claro y perdería contraste sobre estos fondos.

## Don'ts

- No usar `blue-signal` ni `green-signal` como color de texto sobre `canvas`: están calibrados como fondo de bloque con `ink-on-tint` encima, no como color de texto suelto.
- No usar `blue-signal`/`green-signal` fuera de bloques editoriales/de marca (footer, `/quienes-somos`). Las páginas de producto y las señales de precio (`signosDelta()`) se resuelven solo con glifo, peso y relleno acromático — no se les asigna color.
- No agregar un cuarto acento cromático sin actualizar este documento.
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
texto secundario    → 
fondo               → bg-canvas
superficie/hover    → bg-surface
borde/divisor       → border-line
borde de control    → border-line-strong
acento (escaso)     → bg-scarlet-signal / focus:border-scarlet-signal
acento editorial    → bg-blue-signal + text-ink-on-tint (footer, /quienes-somos)
radio               → 0
peso                → 300 (400 solo para el wordmark)
gutter de grid      → gap-element (16px)
salto de sección    → mb-section (80px) · mb-editorial (120px) solo en marketing
```

Los tokens se definen en [global.css](web/src/styles/global.css) y se consumen exclusivamente vía utilidades de Tailwind v4.
