export interface Aviso {
  id: number;
  fuente: 'autocosmos' | 'yapo' | 'autosusados' | 'checkeados';
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
  descripcion: string | null;
  url_imagen: string | null;
  disponible: boolean | null;
  precio_anterior: number | null;
  delta_pct: number | null;
  primera_vez_visto: Date | null;
  ultima_vez_visto: Date | null;
}

export type CategoriaDeal = 'oportunidad_clara' | 'buen_precio' | 'revisar' | 'descartar';

export type FuenteDeal = 'autocosmos' | 'yapo' | 'mercadolibre';

/** Fila de la tabla `deals`: snapshot del aviso + contexto de mercado + evaluación IA. */
export interface Deal {
  id: number;
  fuente: FuenteDeal;
  id_externo: string;
  url: string;
  titulo: string;
  marca: string | null;
  modelo: string | null;
  anio: number | null;
  km: number | null;
  ubicacion: string | null;
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
  fuente?: 'autocosmos' | 'yapo' | 'autosusados' | 'checkeados';
  marca?: string;
  modelo?: string;
  anio?: number;
  precio_min?: number;
  precio_max?: number;
  km_max?: number;
  combustible?: string;
  orden?: 'reciente' | 'precio_asc' | 'precio_desc' | 'km_asc';
  pagina?: number;
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

export interface Estadisticas {
  total_avisos: number;
  total_autocosmos: number;
  total_yapo: number;
  total_autosusados: number;
  total_checkeados: number;
  precio_promedio: number | null;
  precio_minimo: number | null;
  precio_maximo: number | null;
  ultima_actualizacion: Date | null;
}
