export interface Aviso {
  id: number;
  fuente: 'autocosmos' | 'yapo';
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

export interface FiltrosAviso {
  fuente?: 'autocosmos' | 'yapo';
  marca?: string;
  modelo?: string;
  anio?: number;
  precio_min?: number;
  precio_max?: number;
  km_max?: number;
  combustible?: string;
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
  precio_promedio: number | null;
  precio_minimo: number | null;
  precio_maximo: number | null;
  ultima_actualizacion: Date | null;
}
