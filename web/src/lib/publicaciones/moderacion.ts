/**
 * Bandeja de moderación de los avisos de particulares.
 *
 * Todo pasa por el cliente de sesión: las políticas `*_admin` de la migración
 * 0011 son las que autorizan, leyendo `app_metadata.rol` del JWT. Sin rol de
 * administrador estas consultas no devuelven ni modifican nada, así que la
 * comprobación de la ruta es defensa en profundidad y no la única barrera.
 */

import type { SupabaseClient } from '@supabase/supabase-js';

import { TABLA_AVISOS } from './consultas';
import type { EstadoAviso, EstadoReporte } from './opciones';

export const TABLA_REPORTES = 'reportes_aviso';

/** Cuántos reportes trae la bandeja: cabe en una pantalla y evita paginar. */
const TOPE_BANDEJA = 50;

export interface ReporteModeracion {
  id: number;
  aviso_id: number;
  motivo: string;
  detalle: string | null;
  estado: EstadoReporte;
  creado_en: string;
  titulo: string;
  estadoAviso: EstadoAviso;
}

interface FilaReporte {
  id: number;
  aviso_id: number;
  motivo: string;
  detalle: string | null;
  estado: EstadoReporte;
  creado_en: string;
  aviso: { titulo: string; estado: EstadoAviso };
}

/**
 * Los reportes más recientes con el aviso denunciado. El aviso se lee por la
 * política `listings_select_admin`, sin la cual uno ya despublicado saldría del
 * embed y su reporte desaparecería de la bandeja justo tras moderarlo.
 */
export async function listarReportes(supabase: SupabaseClient): Promise<ReporteModeracion[]> {
  const { data } = await supabase
    .from(TABLA_REPORTES)
    .select(`id,aviso_id,motivo,detalle,estado,creado_en,aviso:${TABLA_AVISOS}!inner(titulo,estado)`)
    .order('creado_en', { ascending: false })
    .limit(TOPE_BANDEJA);

  return ((data as unknown as FilaReporte[]) ?? []).map(({ aviso, ...reporte }) => ({
    ...reporte,
    titulo: aviso.titulo,
    estadoAviso: aviso.estado,
  }));
}

/** El aviso denunciado sale del reporte, nunca del formulario. */
export async function avisoDelReporte(
  supabase: SupabaseClient,
  reporteId: number,
): Promise<number | null> {
  const { data } = await supabase
    .from(TABLA_REPORTES)
    .select('aviso_id')
    .eq('id', reporteId)
    .maybeSingle();
  return (data as { aviso_id: number } | null)?.aviso_id ?? null;
}

/**
 * Saca el aviso de la web pública. Deja `disponible` en falso junto con
 * `estado`: la capa de lectura genérica solo conoce esa columna. Su dueño lo
 * sigue viendo en "Mis publicaciones" y puede republicarlo, igual que si lo
 * hubiera pausado él — la sanción es retirar el contenido, no bloquear la cuenta.
 */
export async function despublicarAviso(supabase: SupabaseClient, avisoId: number): Promise<boolean> {
  const { error } = await supabase
    .from(TABLA_AVISOS)
    .update({ estado: 'pausado', disponible: false, actualizado_en: new Date().toISOString() })
    .eq('id', avisoId);

  if (error) console.error('No se pudo despublicar el aviso:', error.message);
  return !error;
}

/** Cierra de una vez todos los reportes pendientes del mismo aviso. */
export async function cerrarReportes(
  supabase: SupabaseClient,
  avisoId: number,
  estado: EstadoReporte,
): Promise<boolean> {
  const { error } = await supabase
    .from(TABLA_REPORTES)
    .update({ estado })
    .eq('aviso_id', avisoId)
    .eq('estado', 'pendiente');

  if (error) console.error('No se pudieron cerrar los reportes:', error.message);
  return !error;
}
