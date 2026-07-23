# CarFlip — Referencia visual

> Galería acromática compuesta por bloques: fondo plano, tipografía en peso whisper, cero radio, y el color reservado a la función. La jerarquía la construyen la composición y la tipografía; el color no decora.

**Temas:** claro (principal) y oscuro (`:root[data-theme="dark"]`).

Este documento es la especificación del sistema. Se lee de arriba a abajo: la marca justifica la composición, la composición justifica los tokens, y los tokens justifican cada componente. Ante una duda que el documento no resuelva, manda el **test de decisión** de la sección 1.

---

## 1. Marca y visión

### Qué es CarFlip

Un recopilador independiente de avisos de autos usados en Chile. Reúne publicaciones de varios portales y automotoras, las normaliza y las ordena bajo un mismo criterio —precio, año, kilometraje, estado— para que comparar deje de tomar una tarde. Nadie paga por aparecer más arriba.

Los principios de la marca están redactados en `/quienes-somos` (constante `principios` de [quienes-somos.astro](web/src/pages/quienes-somos.astro)) y son la fuente de verdad del discurso: las oportunidades se muestran, no se venden; sin fines de lucro; se devuelve el tráfico a la fuente original; código abierto; rápido antes que llamativo.

### Los cuatro principios de diseño

En orden de precedencia. Cuando dos se contradicen, gana el de más arriba.

1. **Simpleza.** La solución más simple que resuelve el problema. No hay premio por la implementación ingeniosa.
2. **Utilidad.** Cada elemento en pantalla responde una pregunta del usuario. Si no responde ninguna, sobra — por bonito que sea.
3. **Atractivo sin saturación.** El sitio se ve trabajado por composición, ritmo y tipografía, no por acumulación de color, efectos o adornos. La contención es el estilo, no una limitación que haya que compensar.
4. **Visión.** El sistema es consistente entre páginas y en el tiempo. Una página nueva se reconoce como CarFlip sin necesidad de leer el header.

### Test de decisión

Se aplica a cada elemento antes de agregarlo:

> 1. **¿Qué pregunta del usuario responde?** Si no responde ninguna, se elimina.
> 2. **¿Se puede resolver con tipografía, espacio o una línea de 1px** en vez de con color, caja o efecto? Si se puede, se hace así.
> 3. **¿Sobrevive en tema oscuro, a 320px y con `prefers-reduced-motion`?** Si no, no está terminado.
> 4. **¿Cuesta bytes en el critical path?** Si sí, tiene que ganárselos.

### Tono de voz

El texto es la mitad de la jerarquía en un sistema sin color: lo que en otros productos hace un badge de colores, acá lo hace una palabra bien elegida.

- Español de Chile, segunda persona, sin lenguaje de marketing. *"Compara precios"*, no *"Descubre la mejor experiencia"*.
- Los títulos afirman un hecho, no venden un beneficio: *"Autos bajo precio de mercado"*.
- Los estados vacíos dicen qué pasó y qué hacer: *"Sin datos de marcas para esta fuente. Prueba con otra."*
- Los errores nombran el campo y la corrección esperada, sin culpar: *"Ingresa el kilometraje en números."*
- Los CTAs son verbo + objeto: *"Ver el teléfono del vendedor"*, no *"Continuar"*.
- Las cifras van con su unidad y su marco temporal: *"1.240 avisos · últimas 24 h"*.
- Nunca signos de exclamación. Nunca mayúsculas para enfatizar (las versalitas de rótulo son otra cosa: son estructura, no énfasis).

---

## 2. Composición

La regla marco:

> **Libertad de composición, sistema invariante.** Cómo se distribuyen los módulos en una página es territorio abierto. Qué son esos módulos, no: radio 0, peso 300, tokens semánticos, ración de color y ausencia de elevación se mantienen en todas las páginas.

El sistema es **minimalista y cubista**: la página se construye con planos rectangulares de distinto peso sobre una misma grilla, no con secciones apiladas de igual tamaño. El interés visual viene de la **asimetría reglada**, no de agregar color ni efectos.

### Reglas

- **Dos pesos como mínimo.** Ninguna sección se compone de módulos todos iguales. Toda sección tiene un módulo dominante —que ocupa al menos la mitad del ancho o abarca varias filas— y módulos subordinados a su alrededor. Un grid de N paneles idénticos apilados es exactamente el defecto que esta sección existe para evitar.
  **Única excepción:** el grid de resultados (`/avisos`, `/deals`), donde la repetición **es** la información y romperla sería mentir sobre la jerarquía de los avisos.
- **La asimetría viene del span, no del margen.** Todos los módulos comparten `gap-element` (16px) y el mismo borde hairline. Lo que cambia es cuántas columnas y filas ocupa cada uno. Una composición nunca se corrige con márgenes ad-hoc.
- **Alternancia de eje.** Si una sección apila en vertical, la siguiente distribuye en horizontal. Dos secciones consecutivas con el mismo eje y el mismo ritmo es el síntoma de la página lineal.
- **Un rompe-columna por página como máximo.** Un solo módulo puede salirse del contenedor y llegar al borde real de la ventana (el truco `w-screen`/`50vw` que ya usa la banda de deals destacados; ver la nota de `overflow-x` en [global.css](web/src/styles/global.css)). Más de uno y deja de ser un acento.
- **La densidad se resuelve con ritmo, no con aire.** Antes de agregar 40px de separación, cambiar el peso o el eje de los módulos. El espacio vertical extra hunde contenido bajo el fold sin resolver la monotonía.
- **El colapso ordena por importancia.** Bajo `md:` el bento pasa a una columna y el módulo dominante va primero, aunque en escritorio no sea el primero del DOM.

### Prohibido

Diagonales, `clip-path` decorativo, rotaciones, solapes entre módulos, sombras y gradientes. La profundidad la dan el vacío y las líneas de 1px — esto no contradice la sección *Elevación*, la refuerza.

### Ejemplo

```
✗ Lineal                        ✓ Modular asimétrico
┌───────┬───────┬───────┐      ┌───────────────┬───────┐
│   A   │   B   │   C   │      │               │   B   │
├───────┼───────┼───────┤      │       A       ├───────┤
│   D   │   E   │   F   │      │               │   C   │
├───────┼───────┼───────┤      ├───────┬───────┴───────┤
│   G   │   H   │   I   │      │   D   │       E       │
└───────┴───────┴───────┘      ├───────┴───────┬───────┤
                               │       F       │   G   │
mismo peso nueve veces:        └───────────────┴───────┘
la vista no encuentra          un dominante por bloque,
dónde empezar                  mismo gutter, mismo borde
```

El bento de `/mercado` es hoy el caso a corregir: nueve `Panel` de peso casi idéntico (ver *Pendientes de alineación con el código*).

---

## 3. Movimiento

Nada aparece de golpe, y nada se hace esperar. El presupuesto es **fijo y discreto**:

```
opacidad   0 → 1
duración   200ms
curva      ease-out
sin desplazamiento · sin escala · sin stagger
```

Un solo valor de duración para todo el sistema. Si un movimiento pide más tiempo o más recorrido que este presupuesto, la respuesta es que no lleva movimiento.

El presupuesto rige sobre el **contenido**. El chrome —hoy solo la barra de navegación— puede además cambiar de alto y retraerse, porque ahí el movimiento no compite con la lectura: es el marco haciéndose a un lado. Conserva los mismos 200ms y la misma curva.

### Capas permitidas

Son seis y no hay una séptima. Todas se condicionan a `prefers-reduced-motion` y todas degradan a contenido visible y funcional.

| Capa | Técnica | Regla |
| ---- | ------- | ----- |
| **Entrada por scroll** | CSS puro: `animation-timeline: view()` con `animation-range: entry`, dentro de `@supports` | Cero JS, cero `IntersectionObserver`. Sin soporte, el contenido nace visible. **Nunca** sobre contenido above-the-fold ni sobre el elemento LCP: animar su opacidad retrasa el LCP y cuesta puntos de Performance |
| **Estado e interacción** | `transition-colors` / borde a 200ms | Hover, foco y `checked`. Sin `transform`: las cards no se levantan ni se escalan |
| **Datos en gráficos** | Barras, áreas y sparklines que crecen desde 0, ligadas a `view()` | Única excepción donde se permite `transform`. Solo dentro de un panel de gráfico, una sola vez, sin escalonar entre series |
| **Navegación entre páginas** | `@view-transition { navigation: auto; }` en `global.css` | Cross-fade nativo cross-document, **cero JS**. No se usa el `ClientRouter` de Astro: sus ~7 KB no se justifican cuando el CSS nativo hace lo mismo. Sin soporte, navegación normal |
| **Cambio de tema** | `document.startViewTransition()` en el toggle ya existente | Cross-fade de 200ms con API nativa, 0 bytes extra. Con detección de soporte; si no existe o hay reduced-motion, el tema cambia igual, instantáneo. El script bloqueante del `<head>` no se toca: el primer pintado nunca se anima |
| **Barra de navegación** | Encogimiento **continuo**: un `--p` de 0 a 1 escrito por JS, interpolado en CSS con `calc()`, sin `transition`. El retraerse sí es un estado: `translateY(-100%)` a 240ms | Única capa que responde a la dirección del scroll, que el CSS todavía no sabe leer: por eso lleva JS, con listener pasivo y un solo `requestAnimationFrame` por frame. Es también la única que admite desplazamiento, y solo sobre el chrome: la barra se retrae, el contenido nunca se mueve |

### Excepción above-the-fold

El hero del home (título, promesa y buscador) entra con la utilidad `.entrada` de `global.css`, pese a contener el elemento LCP. La condición que lo hace admisible es **no llevar `animation-delay`**: el navegador contabiliza el pintado en cuanto la opacidad supera 0, así que el costo real es de un frame y no de los 200ms completos. El fade se aplica al bloque, nunca a cada elemento, para que no haya escalonado.

Es la única excepción. Cualquier animación above-the-fold con `delay`, desplazamiento o stagger sigue prohibida, porque esas sí retrasan el LCP por su duración completa.

### Criterio

> Si la animación se espera, es demasiado larga. Si no se nota que algo entró, es innecesaria.

---

## 4. Tokens — Color

Los nombres son **semánticos**, no cromáticos: el mismo token cambia de valor según el tema. Nunca escribir un hex en un componente; siempre la utilidad Tailwind del token.

| Token             | Utilidad Tailwind | Claro     | Oscuro    | Rol                                                             |
| ----------------- | ----------------- | --------- | --------- | --------------------------------------------------------------- |
| `--c-canvas`      | `canvas`          | `#ffffff` | `#000000` | Fondo de página, header, footer, relleno de badges sobre imagen |
| `--c-surface`     | `surface`         | `#f4f4f4` | `#101010` | Placeholder de imagen, hover de filas, elevación mínima         |
| `--c-ink`         | `ink`             | `#000000` | `#ffffff` | **Todo el texto**, títulos, precios, bordes en hover y estado activo |
| `--c-muted`       | `muted`           | `#5f5f5f` | `#a0a0a0` | **No es color de texto.** Rellenos de gráfico, `placeholder`, categoría "Otros" |
| `--c-line`        | `line`            | `#dcdcdc` | `#484848` | Bordes de card, divisores, paginación deshabilitada             |
| `--c-line-strong` | `line-strong`     | `#767676` | `#a0a0a0` | Bordes de inputs, selects y badges (necesitan 3:1 de contraste)  |
| `--c-scarlet`     | `scarlet-signal`  | `#e4002b` | `#e4002b` | **Solo borde y objeto gráfico**: foco, campo inválido, botón destructivo |
| `--c-blue`        | `blue-signal`     | `#1873b3` | `#1873b3` | Acento editorial: fondo de bloques de marca (footer, hero de `/quienes-somos`) y lavado rotativo del mosaico de principios de esa misma página |
| `--c-green`       | `green-signal`    | `#71db4c` | `#71db4c` | Acento editorial secundario, mismo régimen que `blue-signal`; reservado, sin implementación asignada |
| `--c-ink-on-tint` | `ink-on-tint`     | `#ffffff` | `#ffffff` | Blanco fijo para texto sobre `blue-signal`/`green-signal`; no invierte con el tema |
| `--c-github`      | `github-signal`   | `#181717` | `#181717` | Negro de marca de GitHub, solo para el ícono del footer; no es un acento del sistema |

### Sin texto gris

**No existe un token de texto secundario.** Todo texto va en `ink`. El único matiz permitido es la opacidad, y está reglado:

| Nivel | Utilidad | Dónde | Claro | Oscuro |
| ----- | -------- | ----- | ----- | ------ |
| Primario | `text-ink` | Títulos, precios, copy, valores, enlaces | 21:1 | 21:1 |
| Secundario | `text-ink/70` | Metadatos, rótulos, notas al pie de cifra, ejes de gráfico | 8.52:1 sobre `canvas` · 8.16:1 sobre `surface` | 9.96:1 sobre `canvas` · 9.52:1 sobre `surface` |

Reglas de la opacidad:

- `/70` es el único escalón. No hay `/60` ni `/50`: cada paso adicional es un gris nuevo por la puerta de atrás.
- **Solo sobre `canvas` o `surface`.** La opacidad compone contra el fondo real, así que sobre un badge `bg-canvas/75` (que a su vez deja pasar la foto) o sobre `blue-signal` los números de arriba no aplican: ahí el texto va en `ink` sólido o en `ink-on-tint`.
- Si la distinción que se busca es de jerarquía y no de segundo plano, se resuelve antes con tamaño, versalitas o espacio que con opacidad.

### Piso de contraste

**El sistema exige 7:1 (AAA) para todo texto, en ambos temas.** Lighthouse mide contra 4.5:1; el margen existe para que el 100 de Accessibility no dependa de un redondeo ni de un cambio menor de token. Los objetos gráficos (bordes de control, glifos, marcas de gráfico) mantienen el piso de 3:1 que exige AA.

De ahí sale la restricción del escarlata: como texto rinde **4.85:1 en claro y 4.33:1 en oscuro** —el segundo ya está bajo AA—, así que **el escarlata no se usa como color de texto**. Vive en el borde: foco, campo inválido, botón destructivo. Un error de formulario se comunica con el borde escarlata más el texto del error en `ink`; un campo obligatorio, con la palabra `*Requerido`, no con su color.

### Acentos de fondo (`blue-signal` / `green-signal`)

`blue-signal` y `green-signal` solo se usan como **fondo de bloque** (footer, hero de `/quienes-somos`), nunca como color de texto sobre `canvas`, y el texto que va encima siempre es blanco (`ink-on-tint`), no `ink`: `ink` es negro en tema claro y perdería contraste sobre estos fondos.

| Fondo                              | Contraste con blanco |
| ----------------------------------- | --------------------- |
| `blue-signal` (`#1873b3`)           | 5.07:1 — pasa AA      |
| `green-signal` (`#71db4c`, sin implementar) | 1.76:1 — fallaría AA  |

`blue-signal` se profundizó a propósito desde el azul pedido originalmente (`#43a8ee`): ese tono solo daba 2.6:1 con blanco, bajo el 4.5:1 que exige AA. `#1873b3` conserva la misma familia de azul pero con luminancia suficiente para que el texto blanco cumpla. Si `green-signal` llega a implementarse con texto encima, necesita el mismo ajuste antes de usarse — el `#71db4c` documentado es el tono pedido, no uno ya verificado para texto.

### Cambio de tema

El tema se aplica con `data-theme="dark"` en `<html>` y se persiste en `localStorage` bajo la clave `tema` (`'claro' | 'oscuro'`). Un script inline y bloqueante en `<head>` lo aplica antes del primer pintado para evitar el flash. La variante `dark:` de Tailwind está redefinida con `@custom-variant` para seguir el atributo, no el media query del sistema: manda la preferencia guardada. El cross-fade al alternar es la quinta capa de movimiento (sección 3).

---

## 5. Tokens — Tipografía

**Sin webfonts.** Se usa el stack de sistema por defecto de Tailwind (`ui-sans-serif, system-ui, …`). Es una decisión de rendimiento: cero requests de fuente, cero FOUT, cero peso en el critical path. No introducir `@font-face` sin una razón que justifique el costo en Core Web Vitals.

**Pesos:** solo 300 y 400. El `body` es 300 por defecto y `h1/h2/h3` también: el peso whisper es la firma del sistema. No usar 600+.

**Tracking:** se aprieta a medida que crece el tamaño — `-0.01em` en body, `-0.02em` en títulos. Ambos son globales en `global.css`; no repetirlos por elemento.

Sin color y con un solo peso disponible, **la jerarquía la cargan el tamaño, las versalitas y el espacio**. Un rótulo se distingue por ser `text-sm uppercase tracking-wider`, no por ser gris; un dato importante, por ser `text-2xl`, no por estar en negrita.

### Escala en uso

El tramo de lectura (`sm` … `2xl`) está **corrido un paso hacia arriba** respecto de los valores por defecto de Tailwind: a peso 300, 16px sobre una columna de `max-w-3xl` quedaba bajo el umbral cómodo de lectura. La corrección se hace en los tokens `--text-*` de `global.css`, no clase por clase, así que alcanza a todo el sitio de una vez. De `text-3xl` en adelante —métricas y displays— se conservan los valores de Tailwind: ya estaban dimensionados.

| Rol                          | Utilidad                | Tamaño        | Dónde                                                      |
| ---------------------------- | ----------------------- | ------------- | ---------------------------------------------------------- |
| Label / badge                | `text-sm`               | 15px          | Labels de filtro (`uppercase tracking-wider`), fuente, riesgos |
| Body / nav / meta            | `text-base`             | 17px          | Texto de producto: copy de UI, nav, metadatos, botones, paginación |
| Párrafo editorial            | `text-lg`               | 19px          | Copy de lectura corrida: `/como-funciona`, `/quienes-somos` y las páginas legales — vía `parrafoCls` |
| —                            | `text-xl`               | 22px          | Sin rol asignado                                            |
| Precio de card / h2          | `text-2xl`              | 26px          | Precio en `CardAviso`/`CardDeal`, títulos de sección       |
| Métrica interna              | `text-3xl` / `text-4xl` | 30 / 36px     | Solo `/dashboard`                                          |
| H1 de página / cifra hero    | `text-5xl sm:text-7xl`  | 48 → 72px     | H1 de cada página y la cifra de portada, con `leading-none` |

Los `line-height` por defecto de Tailwind son ratios sin unidad, así que escalan solos con el tamaño; no hay que redefinirlos al mover la escala.

Los números siempre con `tabular-nums`: precios, kilometrajes, porcentajes y contadores no deben bailar entre filas.

### Texto de producto vs. párrafo editorial

Son dos registros distintos y no deben mezclarse:

- **Producto** (`/avisos`, `/deals`, `/mercado`, cards, formularios, `/dashboard`): `text-base`. Se escanea, no se lee; las líneas son cortas y la densidad importa.
- **Editorial** (`/como-funciona`, `/quienes-somos`, `/condiciones-de-uso`, `/privacidad`, `/legal`): `text-lg leading-relaxed` sobre `max-w-3xl`. Se lee de corrido, así que pide un paso más de tamaño y más interlínea.

El registro editorial está centralizado en `parrafoCls`, exportado desde [marketing.ts](web/src/lib/marketing.ts) junto a `seccionCls` y `rubroCls`. Los párrafos largos usan esa constante —nunca `text-lg leading-relaxed` escrito a mano— para que un cambio de ritmo de lectura siga siendo un solo edit.

---

## 6. Tokens — Espaciado y forma

El ritmo vertical está adaptado al producto. Los 120/240px de portafolio hundirían un grid de 24 avisos bajo el fold, así que `editorial` se reserva a páginas de marketing (`/`, `/como-funciona`).

| Token                 | Utilidad     | Valor | Uso                                                          |
| --------------------- | ------------ | ----- | ------------------------------------------------------------ |
| `--spacing-element`   | `*-element`  | 16px  | Gutter de grids, padding de cards, gaps internos              |
| `--spacing-block`     | `*-block`    | 48px  | Separación entre bloques dentro de una sección, padding de `<main>` en desktop |
| `--spacing-section`   | `*-section`  | 80px  | Separación entre secciones, margen superior del footer y de la paginación |
| `--spacing-editorial` | `*-editorial`| 120px | Respiro máximo entre secciones, solo en páginas editoriales (`lg:` en adelante) |

**No usar `inline-block`.** Tailwind deriva utilidades de `inline-size` desde el namespace `--spacing-*`, así que `--spacing-block` genera un segundo `.inline-block { inline-size: 48px }` que pisa el ancho del elemento. Para un enlace o un badge que deba tener ancho propio, usar `inline-flex`, que es además el idioma del resto del sitio.

### Radio

**Todos los radios son 0px**, incluidas todas las variantes de Tailwind (`--radius-xs` … `--radius-4xl`). Si sobrevive algún `rounded-*` en el código queda inerte por construcción. No reintroducir esquinas redondeadas.

---

## 7. Layout

- Contenedor único: `max-w-7xl mx-auto px-4 sm:px-6 lg:px-8`. Header, `main` y footer comparten el mismo, así que todo se alinea a la misma columna.
- `<body>`: `flex flex-col min-h-screen`, `main` con `flex-1` — el footer queda abajo aunque la página sea corta.
- Header: el `<header>` reserva 80px en el flujo y la barra va `fixed inset-x-0 top-0 z-20`, fondo `canvas` sin borde ni blur. La barra se funde con el canvas. Al ir fuera del flujo, su cambio de alto no empuja el contenido: el layout shift queda en 0.
- `main`: `py-8 lg:py-block`.
- Grid de resultados: `grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-element`. En `/avisos` convive con un sidebar de `lg:w-48` sticky.
- Bento de estadística: `grid-cols-1 md:grid-cols-2 lg:grid-cols-6`, con módulos de span desigual según la sección 2.

### Breakpoints

| | S | M | L | XL |
|-|---|---|---|----|
| Tailwind | base | `sm:` 640px | `lg:` 1024px | `xl:` 1280px+ |
| Qué cambia | 1 columna, sidebar colapsado tras un toggle, nav plegada en el menú | 2 columnas, tipografía hero a 72px | 3 columnas, sidebar visible, `lg:py-block`, saltos `editorial` | Solo más aire lateral; el contenido tope en `max-w-7xl` |

A 320px no caben seis enlaces de nav más el wordmark y el toggle, así que bajo `md:` (768px) la nav entera se pliega tras la hamburguesa. Es un `<nav>` único: las mismas `<li>` se pintan en fila arriba de `md:` y apiladas dentro del desplegable abajo. Ningún enlace se oculta por ancho.

---

## 8. Estructura del sitio

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
| `/cuenta`          | Resumen `noindex` del área privada: métricas de actividad, últimas publicaciones, datos de contacto y baja de cuenta plegada |
| `/cuenta/avisos`   | "Mis publicaciones": listado completo de `FilaAviso` con estado y acciones en línea |
| `/cuenta/avisos/nuevo`, `/cuenta/avisos/[id]/editar` | Formulario de publicación (`FormularioAviso` + `SubidorFotos`) |
| `/dashboard`       | Métricas operacionales internas y bandeja de moderación de reportes       |

---

## 9. Componentes

### Header

Dos zonas: izquierda, wordmark `CarFlip` en `font-normal text-ink` seguido del descriptor "Comparador de autos Chile" en `text-ink/70` (solo `lg:`); derecha, la nav, el toggle de tema y —bajo `md:`— la hamburguesa. Enlaces en `text-base`, `text-ink/70` en reposo y `ink` con `underline underline-offset-4` cuando están activos. `/` solo marca activo en coincidencia exacta; el resto también en sus subrutas (`/marcas/Kia` resalta Mercado, `/auto/814` resalta Avisos), vía `aria-current="page"`.

**El encogimiento es continuo, no un estado.** El script escribe en `#barra` una variable `--p` que mapea el scroll a un 0…1 sobre los primeros 80px, y el CSS interpola con `calc()`:

```
alto      calc(5rem - 2rem * var(--p))        →  80px … 48px
wordmark  calc(text-2xl - (2xl - base) * p)   →  26px … 17px
```

Sin `transition` de por medio: la barra va pegada al scroll en vez de dispararse por umbral y tardar 200ms en llegar. Un encogimiento por umbral se lee como un escalón; uno continuo se lee como una sola superficie que responde.

A los 80px la barra queda exactamente como la de 48px de siempre, así que lo que se agrega es un estado expandido al tope, no un rediseño.

Los otros dos estados sí son atributos sobre `#barra`, porque no dependen de una posición:

| Estado | Cuándo | Qué hace |
| ------ | ------ | -------- |
| `data-oculta` | al bajar, pasados 160px | `translateY(-100%)` a 240ms con curva exponencial; vuelve al subir |
| `data-menu` | menú desplegado (solo bajo `md:`) | bloquea `data-oculta`, porque el panel cuelga de la barra |

`data-oculta` se conmuta **con histéresis de 24px**: el momentum y el rebote del trackpad invierten el sentido del scroll por uno o dos píxeles, y sin umbral la barra parpadea en cada micro-cambio. El ancla se reubica al cambiar de sentido y recién conmuta tras recorrer esos 24px en el sentido nuevo.

`#barra:focus-within` cancela `data-oculta` para que quien navega con teclado nunca quede tabulando sobre algo fuera de pantalla. Con `prefers-reduced-motion` la barra queda quieta en su forma compacta: ni encoge ni se retrae.

### Menú móvil

Bajo `md:` la nav se despliega desde la barra como un bloque a ancho completo: `bg-canvas`, hairlines `border-y border-line`, enlaces apilados con `divide-y divide-line` y `py-3` (target táctil de ~48px). Sin sombra, sin radio, sin overlay — es un plano más del sistema, no una capa flotante.

El disparador es un `<button>` con `aria-expanded` y `aria-controls`; los dos glifos (≡ y ✕) se alternan por CSS según ese mismo `aria-expanded`, sin atributo extra. Cierra con Escape (devolviendo el foco al botón), con clic fuera de la barra o navegando. Como el panel precede al botón en el DOM, al abrirlo el foco se lleva a su primer enlace.

### Toggle de tema

Botón de 40×40 (target táctil) con dos SVG inline —luna y sol— que se alternan con `dark:hidden` / `hidden dark:block`. El `aria-label` se reetiqueta por JS al estado destino ("Cambiar a tema oscuro" / "claro"). El cambio va envuelto en `document.startViewTransition()` cuando existe (sección 3).

### CardAviso

`<article>` con `border border-line`, hover a `border-ink` en 200ms. Sin radio, sin sombra, sin transform. La imagen es `aspect-[4/3] object-cover` sobre `bg-surface`; su borde ES el borde de la card. Badges absolutos arriba a la izquierda sobre `bg-canvas/75`, con el texto en `ink` sólido —nunca `/70`, porque el fondo del badge deja pasar la foto—: fuente, variación de precio y, si aplica, "No disponible" tachado. Cuerpo con `p-element`: título en `text-base line-clamp-2`, precio en `text-2xl text-ink tabular-nums`, y metadatos (`año · km · ubicación`) unidos con ` · ` en `text-ink/70`, en una sola línea con `truncate`.

### CardDeal

Misma anatomía, imagen `aspect-[16/10]`. La diferencia es el badge de categoría IA arriba a la derecha, que **jerarquiza por relleno y borde, no por color**:

| Categoría           | Estilo                                  |
| ------------------- | --------------------------------------- |
| `oportunidad_clara` | `bg-ink text-canvas`                    |
| `buen_precio`       | `bg-canvas text-ink border-ink`         |
| `revisar`           | `bg-canvas text-ink border-line-strong` |
| `descartar`         | `bg-canvas text-ink border-line`        |
| `sin_evaluar`       | `bg-canvas text-ink border-line`        |

La etiqueta de texto siempre acompaña, así que no se pierde información sin el color. Debajo del precio conviven el puntaje IA (`n/100`), el % vs mercado, la bajada propia del aviso, hasta 3 chips de riesgo con `+n` de overflow, y el resumen de la IA en `line-clamp-2`.

### Badge "Particular"

Los avisos publicados en el sitio llevan el mismo badge de fuente que los recopilados, con la etiqueta `Particular`, y comparten card, grid, filtros y señales de precio. La decisión de diseño es que **no se distinguen visualmente**: son una fuente más del listado, y darles un tratamiento propio sugeriría una jerarquía que el producto no tiene. Lo único distinto es el destino del enlace, que resuelve `enlaceAviso()`: `/auto/p/<id>` en vez de `/auto/<id>`.

### Galería del aviso de particular

Carrusel horizontal de `scroll-snap` (`snap-x snap-mandatory`) con las fotos a `aspect-[16/9] object-cover`, y miniaturas debajo que son `<a href="#foto-n">` sobre los `<li>` del carrusel. **Cero JavaScript y cero layout shift**: cada foto lleva `width`/`height` explícitos y la caja no depende de la imagen. La primera va `loading="eager"` + `fetchpriority="high"` + `decoding="sync"` porque es el LCP —y por eso mismo nunca lleva animación de entrada—; el resto, `lazy`. El desplazamiento suave va tras `motion-safe:`.

### Bloque de contacto

Cierra el detalle de un aviso de particular, tras `border-t border-line`. Tiene tres estados y el servidor decide cuál pinta:

| Estado             | Qué se ve                                                                 |
| ------------------ | ------------------------------------------------------------------------- |
| Anónimo            | CTA que lleva a `/entrar?volver=…`. El teléfono no está en el HTML         |
| Con sesión         | CTA "Ver el teléfono del vendedor" (POST) y el aviso de que el vendedor verá el interés |
| Ya revelado        | Nombre en `text-2xl`, número en `text-3xl sm:text-5xl tabular-nums`, y los botones Llamar y WhatsApp |

El número escala recién en `sm:` porque sus 14 caracteres a `text-5xl` se salen de una pantalla de 320px. El teléfono nunca se renderiza oculto: si no corresponde mostrarlo, no llega al HTML — tampoco al JSON-LD, cuyo `seller` va sin nombre ni número.

### Señales de variación de precio

`signosDelta()` devuelve glifo + token, nunca verde ni rojo: bajada → `▼ n%` en `text-ink` (gana peso porque es la buena noticia), alza → `▲ n%` en `text-ink` sobre el mismo `bg-canvas/75`. El glifo carga el significado; el color no interviene.

### Formularios

Inputs y selects: `bg-canvas border border-line-strong px-3 py-2`, foco con `focus:outline-hidden focus:border-scarlet-signal`. La validación es nativa (`:user-invalid`), sin JS: el campo inválido pinta su **borde** en `scarlet-signal` y muestra el mensaje de error debajo en `text-ink`. El marcador de campo obligatorio es la palabra `*Requerido` en `text-sm text-ink`, no un color. El botón destructivo (eliminar cuenta, despublicar) lleva borde `scarlet-signal` con texto `ink`, e invierte a `bg-scarlet-signal text-ink-on-tint` en hover.

### FiltrosBarra

Bloque sobre el listado, cerrado con `border-b border-line`. Fuente como `fieldset` de radios ocultos (`sr-only peer`) con etiquetas tipo toggle: `border-line-strong` en reposo, `peer-checked:bg-ink peer-checked:text-canvas`. Debajo, selects de marca y año, más las acciones a la derecha: "Filtrar" con borde `ink` y "Limpiar" como enlace. A anchos chicos se apila en dos bloques.

### FiltrosSidebar

`aside` de `lg:w-48`, `lg:sticky lg:top-20`. En mobile está oculto tras un botón toggle que, cuando hay filtros aplicados, lo dice con **texto y cantidad** —"Filtros avanzados (2)"—, no con una marca de color: el conteo informa más y sobrevive al daltonismo y al tema oscuro. Un único set de inputs para no duplicar campos al enviar el form.

### Paginacion

Solo se renderiza con más de una página. Ventana de ±2 alrededor de la actual, con `1 … n` en los extremos. Página actual en `bg-ink text-canvas`; el resto `text-ink/70 → ink` en hover; deshabilitados en `text-line` con `aria-disabled` (son objeto gráfico inerte, no texto legible: no aplica el piso de 7:1).

### Lista "Explorar"

Filas apiladas con `divide-y divide-line border-y border-line`, sin cajas. Cada fila: título en `text-2xl text-ink` con ancho fijo, detalle en `text-ink/70`, flecha `→` a la derecha, hover a `bg-surface`. Prueba de que el texto apilado estructura mejor que una grilla de tarjetas.

### Bloque de cifras

Pares label/valor sin bordes ni cajas: label en `text-base text-ink/70`, valor justo debajo en `text-base text-ink tabular-nums`. Se distribuyen con `flex flex-wrap gap-x-block gap-y-element`. La tipografía hace el trabajo de estructurar.

### CTA primario

`inline-flex` con borde `ink`, `px-6 py-3`, hover que invierte a `bg-ink text-canvas`. Es el único botón con presencia; el resto de acciones son enlaces o botones con borde. No lleva marca de color: la inversión en hover y el borde sólido ya lo separan de todo lo demás en pantalla.

### Panel (bento de estadística)

`<section>` con `border border-line`, cabecera de `p-element` cerrada con `border-b border-line` —título en `text-base text-ink`, subtítulo opcional en `text-sm text-ink/70`— y el gráfico en un `flex-1 min-h-0` para que llene la altura cuando el módulo abarca varias filas. **El panel es el módulo de la grilla de la sección 2**: su `class` recibe el span (`lg:col-span-4`, `lg:row-span-2`) y esa asignación no es cosmética, es la que evita que la página quede plana.

### NavCuenta

Barra de pestañas del área privada (`Resumen` · `Mis publicaciones`), repetida en `/cuenta` y `/cuenta/avisos`. Contenedor con `border-b border-line`; cada pestaña es un enlace de `py-3` con `border-b` de 1px —`border-ink` cuando está activa, `border-transparent` en reposo— y la lista lleva `-mb-px` para que el subrayado activo se monte sobre el borde del contenedor. Marca la activa con `aria-current="page"`, y las subrutas de un aviso (`nuevo`, `editar`) siguen resaltando "Mis publicaciones". Existe porque el área privada son dos páginas y antes lo único que las unía era un enlace suelto al pie del formulario.

### FilaAviso

Fila de un aviso propio, compartida por el resumen de `/cuenta` y el listado de `/cuenta/avisos`. Miniatura `w-28 aspect-[4/3] object-cover` sobre `bg-surface` —lo que vuelve reconocible cada fila de un vistazo— y, a su lado, la anatomía de `CardAviso`: título en `text-base text-ink truncate`, precio en `text-2xl tabular-nums`, metadatos (`año · km · ubicación`) en `text-ink/70` y una línea final de rendimiento (`vistas · contactos revelados`) en `text-sm`. Miniatura y datos forman **un solo enlace** a la edición, así que "Editar" desaparece de las acciones; el slot queda para las de estado (Pausar/Republicar, Marcar vendido, Ver aviso) como enlaces subrayados. El estado jerarquiza por relleno y borde, nunca por color, igual que el badge de categoría de `CardDeal`: `publicado` → `bg-ink text-canvas`, `pausado` → `border-line-strong`, `vendido` → `border-line text-ink/70`.

### Bandeja de reportes

Primera sección de `/dashboard`, anclada en `#reportes` y **fuera** del bloque de métricas: los reportes deben verse aunque no haya ninguna corrida de scraping registrada. Caja `border border-line` con cabecera, filas `divide-y divide-line` y las acciones en línea como enlaces subrayados, igual que en "Mis publicaciones" — despublicar es reversible (el autor puede republicar), así que no merece el peso visual de un botón. Los reportes ya revisados se pliegan en un `<details>` nativo, sin JS.

### Footer

`mt-section`, fondo `bg-blue-signal` (el único bloque del sitio con este acento). Todo el texto encima usa `ink-on-tint`, no `ink` ni `ink/70`. Tres zonas en `py-block`: wordmark + tagline + una línea de misión que enlaza a `/quienes-somos`; tres columnas de navegación (Producto: Avisos/Deals/Mercado; Compañía: Quiénes somos/Cómo funciona/Preguntas Frecuentes/Contáctanos/Github, con el ícono de Github inline en `github-signal` — el único color de marca ajeno al sistema, ver sección 4; Legal: Condiciones de Uso/Términos de privacidad/Legales); barra inferior con `border-t border-ink-on-tint/15` y el copyright. Sin CTAs.

---

## 10. Elevación

No hay elevación. El sistema separa con vacío y con líneas de 1px, nunca con sombra, glow ni lift tonal. Las cards viven en el mismo plano que la página y se distinguen solo por su contenido, su borde y su tamaño en la grilla. `surface` existe para placeholders y hovers, no para simular altura.

---

## 11. Imágenes

Las fotos vienen de los portales de origen vía CDN, resueltas por `resolverUrlImagen()`. Reglas:

- `object-cover` en un contenedor con `aspect-ratio` fijo — la caja nunca depende de la imagen, así no hay layout shift.
- `width`/`height` explícitos y `loading="lazy"` en todas las de listado.
- Sin radio, sin padding interno, sin overlays decorativos. Los únicos elementos encima son los badges, sobre `bg-canvas/75`.
- Fallback siempre presente: "Sin imagen" centrado en `bg-surface` con el mismo aspect-ratio.
- `alt` = título del aviso.
- La imagen LCP no lleva animación de entrada (sección 3).

---

## 12. Racionamiento del color

El sistema es mayormente acromático. Hay tres acentos cromáticos y cada uno tiene un rol fijo — no son intercambiables ni conviven en una misma pantalla:

| Acento           | Rol                                                                       | Dónde                                                      |
| ---------------- | -------------------------------------------------------------------------- | ------------------------------------------------------------ |
| `scarlet-signal` | Funcional: marca el estado de un control, nunca decora ni etiqueta.        | Borde de foco, borde de campo inválido, borde del botón destructivo |
| `blue-signal`    | Editorial/institucional: identifica los bloques de marca, no de producto.  | Fondo del footer, hero de `/quienes-somos`, y como lavado de baja opacidad (16%) que rota entre las celdas del mosaico de principios de esa página |
| `green-signal`   | Editorial secundario, mismo régimen que `blue-signal`.                     | Reservado — sin implementación asignada todavía              |

Las páginas de producto (`/avisos`, `/deals`, `/mercado`, `/auto/[id]`, cards) son acromáticas de punta a punta: el escarlata solo asoma cuando el usuario enfoca un control o deja un campo inválido, es decir, en respuesta a una acción y nunca en reposo. `blue-signal`/`green-signal` no aparecen ahí — quedan reservados a los bloques editoriales/de marca.

---

## 13. Paleta de datos (solo gráficos)

Los gráficos de `/mercado` (y futuras vistas de estadística) son la **única excepción** al racionamiento acromático: una serie de datos necesita distinguirse de otra, y con solo `ink`/`line` no alcanzan las categorías. Es un presupuesto cromático **acotado y exclusivo de la visualización** — no toca el chrome del producto. Fuera de un `<svg>`/panel de gráfico, esta paleta no se usa.

| Token       | Utilidad Tailwind | Valor      | Rol en el gráfico          |
| ----------- | ----------------- | ---------- | -------------------------- |
| `--c-viz-1` | `viz-1`           | `#1b6faf`  | Categórica 1 (azul)        |
| `--c-viz-2` | `viz-2`           | `#a15c00`  | Categórica 2 (ocre)        |
| `--c-viz-3` | `viz-3`           | `#0e8f7d`  | Categórica 3 (teal)        |
| `--c-viz-4` | `viz-4`           | `#8a3fb0`  | Categórica 4 (violeta)     |
| `--c-scarlet` | `scarlet-signal` | `#e4002b` | Realce de **un** dato focal |

Mismo valor en ambos temas (como `scarlet`/`blue`): la paleta fue verificada con `scripts/validate_palette.js` de la skill *dataviz* y pasa las seis comprobaciones (banda de luminosidad, piso de croma, separación CVD, piso de visión normal y contraste) sobre superficie clara `#ffffff` **y** oscura `#0a0a0a`, así que no se redefine en `[data-theme="dark"]`.

**Reglas de uso:**

- **Categórica** (identidad: mix de combustible, fuentes) → `viz-1…viz-4` en **orden fijo**, nunca cíclico. Una 5.ª categoría **no** genera un quinto tono: se pliega en "Otros" con `muted` (que aquí es relleno, no texto).
- **Magnitud / secuencial** (histogramas, treemap, rankings) → un **solo** tono (`viz-1`, variando opacidad claro→oscuro) o directamente `ink`. Nunca arcoíris.
- **Realce focal** → `scarlet-signal` marca como máximo **un** dato por panel (la marca #1, el bucket destacado). Es la única aparición del escarlata que no responde a una interacción, y por eso está acotada al `<svg>`.
- **Dirección** (subió/bajó de precio) → jamás verde/rojo. Se comunica con glifo `▲▼` + peso, igual que en el resto del sitio (ver `signosDelta()`).
- **El texto nunca lleva el color de la serie**: valores, ejes y leyendas van en `ink` o `ink/70`; el color solo lo carga la marca (barra, punto, segmento) al lado.
- **Entrada animada**: las marcas crecen desde 0 al entrar en viewport, 200ms, sin escalonar (sección 3). Los ejes y las etiquetas no se animan.

---

## 14. Do's

- Componer toda sección con al menos dos pesos de módulo; la única excepción es el grid de resultados.
- Usar siempre los tokens semánticos (`canvas`, `ink`, `line`, `line-strong`, `surface`); nunca un hex ni un `gray-*` de Tailwind.
- Usar `text-ink/70` —y solo sobre `canvas`/`surface`— cuando haga falta un segundo nivel de texto.
- Verificar cada texto contra el piso de 7:1, en **ambos temas**: un color que funciona en claro puede quedar bajo AA en oscuro.
- Mantener todos los radios en 0.
- Usar `tabular-nums` en cualquier número que se repita entre filas.
- Codificar el significado en texto o glifo primero; el color, cuando aparece, es redundante por diseño.
- Usar `element` para densidad, `block`/`section` para respiro de producto, y `editorial` solo en páginas de marketing.
- Bordes de inputs con `line-strong` (3:1); `line` es demasiado sutil para un control interactivo.
- Dar a los targets táctiles al menos 40px de alto.
- Usar `ink-on-tint` para el texto sobre `blue-signal`/`green-signal`.
- Usar `parrafoCls` para todo párrafo de lectura corrida, en vez de escribir `text-lg leading-relaxed` a mano.
- Envolver toda animación en `prefers-reduced-motion` y, si usa `animation-timeline`, también en `@supports`.

## 15. Don'ts

- No apilar módulos del mismo peso uno tras otro: es la definición de página plana (ver sección 2).
- No usar diagonales, rotaciones, solapes ni `clip-path` decorativo para escapar de esa planitud: la salida es la asimetría de la grilla.
- No usar gris para texto — ni `muted`, ni `gray-*`, ni un hex propio. El segundo nivel es `text-ink/70` y no hay un tercero.
- No usar el escarlata como color de texto: no llega a AA en tema oscuro. Vive en el borde.
- No usar `blue-signal` ni `green-signal` como color de texto sobre `canvas`: están calibrados como fondo de bloque con `ink-on-tint` encima.
- No usar `blue-signal`/`green-signal` fuera de bloques editoriales/de marca (footer, `/quienes-somos`).
- No agregar un cuarto acento cromático sin actualizar este documento.
- No usar la paleta de datos (`viz-1`…`viz-4`) fuera de un gráfico.
- No usar sombras, glows ni gradientes en elementos de UI.
- No usar pesos 600+.
- No corregir el tamaño de un texto agregando una clase suelta en un componente: la escala se mueve en los tokens `--text-*` de `global.css`.
- No agregar webfonts sin justificar el costo en Core Web Vitals.
- No usar `dark:` esperando el media query del sistema: la variante está redefinida sobre `data-theme`.
- No centrar párrafos largos; toda copia extensa se alinea a la izquierda.
- No animar contenido above-the-fold con delay, desplazamiento o stagger. El único fade permitido sobre el elemento LCP es el del hero del home (sección 3).
- No introducir JS de cliente para movimiento: ni `ClientRouter`, ni `IntersectionObserver`, ni librerías de animación. La única excepción es la barra de navegación, porque el CSS no sabe leer la dirección del scroll (sección 3).
- No trasladar el ritmo de 120/240px a los listados: hunde los resultados bajo el fold.

---

## Referencia rápida

```
texto primario      → text-ink
texto secundario    → text-ink/70   (solo sobre canvas/surface)
fondo               → bg-canvas
superficie/hover    → bg-surface
borde/divisor       → border-line
borde de control    → border-line-strong
foco / campo inválido → focus:border-scarlet-signal
acento editorial    → bg-blue-signal + text-ink-on-tint (footer, /quienes-somos)
radio               → 0
peso                → 300 (400 solo para el wordmark)
movimiento          → opacidad 0→1 · 200ms · ease-out
texto de producto   → text-base (17px)
párrafo editorial   → parrafoCls (text-lg 19px + leading-relaxed)
gutter de grid      → gap-element (16px)
salto de sección    → mb-section (80px) · mb-editorial (120px) solo en marketing
composición         → un módulo dominante + subordinados, mismo gutter
```

Los tokens se definen en [global.css](web/src/styles/global.css) y se consumen exclusivamente vía utilidades de Tailwind v4.

---

## Pendientes de alineación con el código

Este documento describe el estado objetivo. Al 2026-07-23 el código todavía no lo cumple en estos puntos:

1. **Cuadrado escarlata de 6px** (`<span class="w-1.5 h-1.5 bg-scarlet-signal">`) — sigue presente en `FiltrosBarra`, `FiltrosSidebar`, `CtaAvisos`, `ConsultaMercado`, `FormularioAviso`, `404`, `avisos`, `deals`, `quienes-somos`, `auto/[id]` y `auto/p/[id]`. Se retira sin reemplazo.
2. **`text-muted`** — sobrevive en `web/src/components/mercado/` y `mercado.astro`. Pasa a `ink` o `ink/70`.
3. **Restos del borrado anterior** — clases con espacios sobrantes (`class=" text-base"`, `bg-canvas/75 `) y `rubroCls` en [marketing.ts](web/src/lib/marketing.ts), que quedó sin color de texto tras quitarle `text-muted`.
4. **Escarlata como texto** — mensajes de error y marcador `*Requerido` en `contacto`, `entrar`, `registro` y `FormularioAviso`. Pasan a `ink`; el escarlata queda en el borde. Corrige un fallo AA real en tema oscuro (4.33:1).
5. **Capa de movimiento** — `global.css` ya define la utilidad `.entrada` (opacidad 0→1 · 200ms · ease-out), hoy en uso en el hero del home. Faltan las capas de entrada por scroll, datos en gráficos, `@view-transition` y el cross-fade del toggle de tema.
6. **Bento de `/mercado`** — nueve paneles de peso casi idéntico; hay que recomponerlo según la sección 2.
