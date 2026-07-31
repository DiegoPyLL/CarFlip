/**
 * Clases de los paneles de datos, en un solo lugar.
 *
 * Estaban redeclaradas en /mercado y en la página de marca; con las de modelo y
 * año serían cuatro copias del mismo borde hairline, que es toda la estructura
 * visual de esta familia de páginas.
 */

export const panelCls = 'bg-surface border border-line';

export const cabeceraCls = 'p-element border-b border-line';

export const filaCls = 'flex items-center gap-element p-element hover:bg-canvas transition-colors';

/**
 * Pista de una barra de proporción. El `w-full overflow-hidden` es necesario:
 * sin ancho explícito, el % de la barra interior queda indeterminado durante el
 * sizing intrínseco y dispara el layout.
 */
export const pistaCls = 'h-px w-full bg-line overflow-hidden';

export const enlaceCls = 'text-base text-ink transition-colors';
