/** Listas cerradas de los formularios de publicación. */

// Las 16 regiones, de norte a sur: el orden geográfico es el que espera un
// chileno en un select, no el alfabético.
export const REGIONES = [
  'Arica y Parinacota',
  'Tarapacá',
  'Antofagasta',
  'Atacama',
  'Coquimbo',
  'Valparaíso',
  'Metropolitana',
  "O'Higgins",
  'Maule',
  'Ñuble',
  'Biobío',
  'La Araucanía',
  'Los Ríos',
  'Los Lagos',
  'Aysén',
  'Magallanes',
] as const;

export const COMBUSTIBLES = ['Bencina', 'Diésel', 'Híbrido', 'Eléctrico', 'Gas'] as const;

export const TRANSMISIONES = ['Manual', 'Automática'] as const;

export const ESTADOS_AVISO = ['publicado', 'pausado', 'vendido'] as const;
export type EstadoAviso = (typeof ESTADOS_AVISO)[number];

export const ETIQUETA_ESTADO: Record<EstadoAviso, string> = {
  publicado: 'Publicado',
  pausado: 'Pausado',
  vendido: 'Vendido',
};

export const MOTIVOS_REPORTE = [
  'No es un auto',
  'Precio o datos falsos',
  'Estafa o fraude',
  'Contenido ofensivo',
  'Aviso duplicado',
  'Otro',
] as const;

// Ciclo de vida de un reporte en la bandeja de moderación: se resuelve cuando el
// aviso se despublica, y se descarta cuando el reporte no procede.
export const ESTADOS_REPORTE = ['pendiente', 'resuelto', 'descartado'] as const;
export type EstadoReporte = (typeof ESTADOS_REPORTE)[number];

export const ETIQUETA_REPORTE: Record<EstadoReporte, string> = {
  pendiente: 'Pendiente',
  resuelto: 'Resuelto',
  descartado: 'Descartado',
};

/** El año del auto: se admite el modelo del año siguiente, que ya se vende. */
export const ANIO_MINIMO = 1950;
export const anioMaximo = () => new Date().getFullYear() + 1;
