// Clases compartidas por los formularios y las acciones del área privada
// (/cuenta y sus secciones). Estaban escritas a mano —y con variaciones— en
// cada página, así que un cambio de estilo de campo o de botón eran cuatro
// ediciones. Mismo criterio que `parrafoCls` en marketing.ts.
//
//   campoCls        → input, select y textarea: plano `field` y borde de control
//   labelCls        → etiqueta del campo, con su marcador de obligatorio al ras
//   requeridoCls    → el marcador `*Requerido`
//   errorCls        → mensaje de error del campo (lo muestra global.css)
//   botonCls        → botón o enlace con caja: el CTA del sistema
//   botonPeligroCls → acción destructiva: escarlata de relleno
//   enlaceCls       → enlace de texto sobre canvas o surface
//   enlaceAcentoCls → enlace de texto dentro de un bloque `bg-accent`
//   accionCls       → acción secundaria en línea dentro de una fila
//   volverCls       → enlace de vuelta con flecha, al tope de una página hija

export const campoCls =
  'w-full bg-field border border-line-strong px-4 py-2.5 text-base text-ink focus:outline-hidden focus:border-scarlet-signal transition-colors duration-150';

export const labelCls = 'flex items-baseline justify-between text-base text-ink mb-2';

export const requeridoCls = 'text-sm text-scarlet-signal';

export const errorCls = 'campo-error text-sm text-scarlet-signal mt-1.5';

export const botonCls =
  'inline-flex items-center gap-2 text-base text-ink border border-ink px-6 py-2.5 hover:bg-ink hover:text-canvas transition-colors duration-150 cursor-pointer';

export const enlaceCls =
  'text-base text-ink underline underline-offset-4 hover:text-ink/70 transition-colors duration-150';

export const enlaceAcentoCls =
  'text-base text-ink-on-accent underline underline-offset-4 hover:opacity-70 transition-opacity duration-150 cursor-pointer';

export const accionCls =
  'text-base text-ink/70 underline underline-offset-4 hover:text-ink transition-colors duration-150 cursor-pointer';

// El escarlata va de relleno y no solo en el borde: una baja de cuenta o el
// borrado de una publicación se reconocen antes de leer la etiqueta. El blanco
// encima rinde 4.85:1 en ambos temas (el escarlata es fijo). En hover invierte
// a la versión con borde sobre canvas, que es el idioma del CTA del sitio al
// revés.
export const botonPeligroCls =
  'inline-flex items-center gap-2 text-base bg-scarlet-signal text-ink-on-accent border border-scarlet-signal px-6 py-2.5 hover:bg-canvas hover:text-ink transition-colors duration-150 cursor-pointer';

export const volverCls =
  'inline-flex items-center gap-2 text-base text-ink/70 underline underline-offset-4 hover:text-ink transition-colors duration-150';
