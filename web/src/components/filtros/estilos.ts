/**
 * Clases de los controles de filtro, en un solo lugar.
 *
 * Estaban redeclaradas casi idénticas en BuscadorHome, FiltrosBarra,
 * FiltrosSidebar y deals.astro; cualquier ajuste visual obligaba a tocar los
 * cuatro y a que ninguno se quedara atrás.
 */

const controlBase = [
  'text-base bg-canvas border border-line-strong px-3 py-2',
  'text-ink focus:outline-hidden focus:border-scarlet-signal transition-colors',
].join(' ');

export const inputCls = `w-full ${controlBase} placeholder:text-ink/70`;

export const selectCls = `w-full ${controlBase} appearance-none cursor-pointer`;

export const labelCls = 'block text-sm text-ink/70 uppercase tracking-wider mb-2';

const chipBase = 'px-3 py-2 text-base border border-line-strong hover:border-ink hover:text-ink transition-colors whitespace-nowrap';

/** Chip de un radio `sr-only peer`: el `<span>` hermano es lo que se ve. */
export const chipCls = [
  'block',
  chipBase,
  'peer-checked:bg-ink peer-checked:text-canvas peer-checked:border-ink',
  'peer-focus-visible:border-scarlet-signal',
].join(' ');

/**
 * Chip de un `<button>` que lleva su estado en `aria-pressed` (toolbar de vista
 * y densidad). Es una variante aparte y no el mismo `chipCls`: sin un radio
 * `peer` delante, las variantes `peer-checked:` no aplican nunca y el chip
 * activo se quedaría sin marcar.
 */
export const chipBotonCls = [
  chipBase,
  'aria-pressed:bg-ink aria-pressed:text-canvas aria-pressed:border-ink',
  'focus:outline-hidden focus:border-scarlet-signal cursor-pointer',
].join(' ');
