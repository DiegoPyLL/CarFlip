/**
 * De dónde viene un aviso. Hoy solo los publica un particular; el catálogo de
 * una automotora con acuerdo se sumará como otro miembro de esta unión.
 */
export type Fuente = 'particular';

export interface Aviso {
  id: number;
  fuente: Fuente;
  id_externo: string;
  url: string;
  titulo: string;
  precio: number | null;
  moneda: string;
  marca: string | null;
  modelo: string | null;
  anio: number | null;
  km: number | null;
  ubicacion: string | null;
  combustible: string | null;
  transmision: string | null;
  traccion: string | null;
  descripcion: string | null;
  url_imagen: string | null;
  disponible: boolean | null;
  precio_anterior: number | null;
  delta_pct: number | null;
  primera_vez_visto: Date | null;
  ultima_vez_visto: Date | null;
}

export type CategoriaDeal = 'oportunidad_clara' | 'buen_precio' | 'revisar' | 'descartar';

/** Fila de la tabla `deals`: snapshot del aviso + contexto de mercado + evaluación IA. */
export interface Deal {
  id: number;
  /** Las mismas fuentes que un aviso: `deals` no tiene ninguna propia. */
  fuente: Fuente;
  id_externo: string;
  url: string;
  titulo: string;
  marca: string | null;
  modelo: string | null;
  anio: number | null;
  km: number | null;
  ubicacion: string | null;
  transmision: string | null;
  traccion: string | null;
  precio: number;
  moneda: string;
  url_imagen: string | null;
  precio_mercado: number | null;
  pct_vs_mercado: number | null;
  delta_pct: number | null;
  comparables: number | null;
  categoria: CategoriaDeal | null;
  puntaje: number | null;
  riesgos: string[];
  resumen: string | null;
  categorizado_en: Date | null;
  actualizado_en: Date | null;
}

export interface FiltrosAviso {
  marca?: string;
  modelo?: string;
  anio?: number;
  precio_min?: number;
  precio_max?: number;
  km_max?: number;
  combustible?: string;
  /** Nombre de región de `REGIONES`; se busca dentro de `ubicacion`, que es texto libre. */
  region?: string;
  transmision?: string;
  traccion?: string;
  orden?: 'reciente' | 'precio_asc' | 'precio_desc' | 'km_asc';
  pagina?: number;
}

/**
 * Los filtros de /deals: los mismos campos base más los que solo existen en
 * una selección curada por IA. `orden` no se expone —el ranking lo fija el
 * algoritmo (puntaje, luego pct_vs_mercado)— ni `pagina`, que se resuelve en
 * memoria sobre el top de la corrida.
 */
export interface FiltrosDeal extends Omit<FiltrosAviso, 'orden'> {
  categoria?: CategoriaDeal;
  puntaje_min?: number;
}

export interface PaginaResultado<T> {
  items: T[];
  total: number;
  pagina: number;
  total_paginas: number;
  por_pagina: number;
}

export interface FiltrosDisponibles {
  marcas: string[];
  anios: number[];
  combustibles: string[];
}

/** Los estados que puede tener un aviso, con su conteo. */
export interface ConteoEstados {
  publicado: number;
  pausado: number;
  vendido: number;
}

/** Lo que mide el dashboard: salud del catálogo y de la selección de deals. */
export interface MetricasCatalogo {
  totalAvisos: number;
  porEstado: ConteoEstados;
  nuevos24h: number;
  nuevos7d: number;
  bajadas7d: number;
  /** Publicados sin foto de portada: el KPI de calidad de los avisos. */
  sinFoto: number;
  dealsActivos: number;
  dealsPorCategoria: { categoria: CategoriaDeal; total: number }[];
}

export interface Estadisticas {
  total_avisos: number;
  precio_promedio: number | null;
  precio_minimo: number | null;
  precio_maximo: number | null;
  ultima_actualizacion: Date | null;
}
