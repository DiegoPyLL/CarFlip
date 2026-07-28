/**
 * Acceso a datos de las publicaciones de particulares.
 *
 * Las funciones que reciben un `SupabaseClient` esperan el cliente de sesión
 * (anon key): las políticas RLS son las que autorizan, y nunca comprueban
 * propiedad por su cuenta. Las dos que no lo reciben —`obtenerAvisoPublico` y
 * `telefonoDelVendedor`— leen con el cliente de servicio y documentan por qué.
 */

import type { SupabaseClient } from '@supabase/supabase-js';

import { supabase as servicio } from '@lib/db/client';

import { puedeRevelarContacto } from './limites';
import type { EstadoAviso } from './opciones';

export const TABLA_AVISOS = 'particulares_listings';
export const TABLA_FOTOS = 'particulares_fotos';
export const TABLA_REVELACIONES = 'contacto_revelaciones';
export const BUCKET_FOTOS = 'avisos-particulares';

export interface PerfilUsuario {
  id: string;
  nombre: string | null;
  telefono: string | null;
  region: string | null;
  comuna: string | null;
}

export interface AvisoPropio {
  id: number;
  titulo: string;
  marca: string | null;
  modelo: string | null;
  version: string | null;
  anio: number | null;
  km: number | null;
  precio: number | null;
  patente: string | null;
  combustible: string | null;
  transmision: string | null;
  traccion: string | null;
  ubicacion: string | null;
  descripcion: string | null;
  url_imagen: string | null;
  estado: EstadoAviso;
  visible_en_deals: boolean;
  vistas: number;
  publicado_en: string;
  actualizado_en: string;
}

export interface FotoAviso {
  id: number;
  url: string;
  ruta: string;
  orden: number;
}

/** Lo que ve cualquier visitante en `/auto/p/[id]`: nunca incluye al vendedor. */
export interface AvisoPublico {
  id: number;
  titulo: string;
  marca: string | null;
  modelo: string | null;
  version: string | null;
  anio: number | null;
  km: number | null;
  precio: number | null;
  moneda: string;
  precio_anterior: number | null;
  delta_pct: number | null;
  patente: string | null;
  combustible: string | null;
  transmision: string | null;
  traccion: string | null;
  ubicacion: string | null;
  descripcion: string | null;
  url_imagen: string | null;
  publicado_en: string;
  actualizado_en: string;
  fotos: FotoAviso[];
}

export interface ContactoVendedor {
  nombre: string | null;
  telefono: string;
  /** `tel:` listo para el enlace de llamada. */
  tel: string;
  /** Base de wa.me sin el mensaje: quien la use le añade `?text=`. */
  whatsapp: string;
}

/**
 * Lo que corresponde pintar en el bloque de contacto de un aviso. `pendiente` es
 * el único estado que la página resuelve pidiéndole al lector que lo confirme.
 */
export type ResultadoContacto =
  | { estado: 'ok'; contacto: ContactoVendedor }
  | { estado: 'sin_telefono' }
  | { estado: 'pendiente' }
  | { estado: 'tope' }
  | { estado: 'error' };

const CAMPOS_AVISO =
  'id,titulo,marca,modelo,version,anio,km,precio,patente,combustible,transmision,traccion,ubicacion,descripcion,url_imagen,estado,visible_en_deals,vistas,publicado_en,actualizado_en';

export async function obtenerPerfil(
  supabase: SupabaseClient,
  usuarioId: string,
): Promise<PerfilUsuario | null> {
  const { data } = await supabase
    .from('perfiles')
    .select('id,nombre,telefono,region,comuna')
    .eq('id', usuarioId)
    .maybeSingle();
  return (data as PerfilUsuario) ?? null;
}

export async function listarAvisosPropios(
  supabase: SupabaseClient,
  usuarioId: string,
): Promise<AvisoPropio[]> {
  const { data } = await supabase
    .from(TABLA_AVISOS)
    .select(CAMPOS_AVISO)
    .eq('usuario_id', usuarioId)
    .order('actualizado_en', { ascending: false });
  return (data as AvisoPropio[]) ?? [];
}

export async function obtenerAvisoPropio(
  supabase: SupabaseClient,
  id: number,
  usuarioId: string,
): Promise<AvisoPropio | null> {
  const { data } = await supabase
    .from(TABLA_AVISOS)
    .select(CAMPOS_AVISO)
    .eq('id', id)
    .eq('usuario_id', usuarioId)
    .maybeSingle();
  return (data as AvisoPropio) ?? null;
}

export async function listarFotos(supabase: SupabaseClient, avisoId: number): Promise<FotoAviso[]> {
  const { data } = await supabase
    .from(TABLA_FOTOS)
    .select('id,url,ruta,orden')
    .eq('aviso_id', avisoId)
    .order('orden', { ascending: true });
  return (data as FotoAviso[]) ?? [];
}

const CAMPOS_PUBLICOS =
  'id,titulo,marca,modelo,version,anio,km,precio,moneda,precio_anterior,delta_pct,patente,combustible,transmision,traccion,ubicacion,descripcion,url_imagen,publicado_en,actualizado_en';

/** PostgREST devuelve las columnas `numeric` como texto. */
function aNumero(valor: unknown): number | null {
  return valor === null || valor === undefined ? null : parseFloat(String(valor));
}

/**
 * Aviso publicado con sus fotos, para la página pública de detalle.
 *
 * Lee con el cliente de servicio, igual que el resto de las páginas públicas
 * del sitio, así que el filtro de estado va explícito: aquí no hay sesión sobre
 * la que apoyar la RLS. Devuelve `null` para todo lo que no esté publicado, que
 * es lo que convierte un aviso pausado o vendido en un 404.
 */
export async function obtenerAvisoPublico(id: number): Promise<AvisoPublico | null> {
  const { data } = await servicio
    .from(TABLA_AVISOS)
    .select(`${CAMPOS_PUBLICOS},fotos:${TABLA_FOTOS}(id,url,ruta,orden)`)
    .eq('id', id)
    .eq('estado', 'publicado')
    .maybeSingle();

  if (!data) return null;
  const aviso = data as unknown as AvisoPublico;
  return {
    ...aviso,
    precio: aNumero(aviso.precio),
    precio_anterior: aNumero(aviso.precio_anterior),
    fotos: [...aviso.fotos].sort((a, b) => a.orden - b.orden),
  };
}

/**
 * Teléfono del vendedor de un aviso publicado.
 *
 * Excepción al resto del módulo: `perfiles` solo es legible por su dueño y ni
 * siquiera tiene GRANT para `anon`, así que hace falta el cliente de servicio.
 * Queda acotado a un aviso publicado y a los dos campos que se muestran. Quien
 * llame debe haber comprobado antes que hay sesión y cupo.
 */
export async function telefonoDelVendedor(avisoId: number): Promise<ContactoVendedor | null> {
  const { data } = await servicio
    .from(TABLA_AVISOS)
    .select('perfiles!inner(nombre,telefono)')
    .eq('id', avisoId)
    .eq('estado', 'publicado')
    .maybeSingle();

  const perfil = data?.perfiles as unknown as { nombre: string | null; telefono: string | null } | undefined;
  if (!perfil?.telefono) return null;

  const digitos = perfil.telefono.replace(/\D/g, '');
  return {
    nombre: perfil.nombre,
    telefono: perfil.telefono,
    tel: `tel:+${digitos}`,
    whatsapp: `https://wa.me/${digitos}`,
  };
}

async function contar(consulta: PromiseLike<{ count: number | null }>): Promise<number> {
  const { count } = await consulta;
  return count ?? 0;
}

export function contarCreadosUltimas24h(supabase: SupabaseClient, usuarioId: string): Promise<number> {
  const desde = new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString();
  return contar(
    supabase
      .from(TABLA_AVISOS)
      .select('id', { count: 'exact', head: true })
      .eq('usuario_id', usuarioId)
      .gte('publicado_en', desde),
  );
}

export function contarFotos(supabase: SupabaseClient, avisoId: number): Promise<number> {
  return contar(
    supabase.from(TABLA_FOTOS).select('id', { count: 'exact', head: true }).eq('aviso_id', avisoId),
  );
}

export function contarRevelacionesHoy(supabase: SupabaseClient, usuarioId: string): Promise<number> {
  const desde = new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString();
  return contar(
    supabase
      .from(TABLA_REVELACIONES)
      .select('id', { count: 'exact', head: true })
      .eq('usuario_id', usuarioId)
      .gte('creado_en', desde),
  );
}

/**
 * Si el usuario ya reveló este aviso, la página vuelve a mostrarle el teléfono
 * sin gastar cupo ni duplicar la auditoría: se paga una vez por aviso.
 */
export async function yaReveloContacto(
  supabase: SupabaseClient,
  avisoId: number,
  usuarioId: string,
): Promise<boolean> {
  const total = await contar(
    supabase
      .from(TABLA_REVELACIONES)
      .select('id', { count: 'exact', head: true })
      .eq('aviso_id', avisoId)
      .eq('usuario_id', usuarioId),
  );
  return total > 0;
}

/**
 * Contacto del vendedor si este lector ya reveló este aviso. **No escribe nada.**
 *
 * Es lo que consulta la página de detalle, que es un GET: registrar ahí gastaba
 * el cupo diario del usuario sin que él lo pidiera, y `checkOrigin` de Astro no
 * cubre GET, así que un sitio externo podía agotarle las revelaciones del día
 * mandándolo a recorrer avisos. El registro vive en `revelarContacto`, detrás de
 * un POST. `pendiente` es «hay teléfono, falta que lo pida».
 */
export async function contactoRevelado(
  supabase: SupabaseClient,
  avisoId: number,
  usuarioId: string,
): Promise<ResultadoContacto> {
  const contacto = await telefonoDelVendedor(avisoId);
  if (!contacto) return { estado: 'sin_telefono' };
  return (await yaReveloContacto(supabase, avisoId, usuarioId))
    ? { estado: 'ok', contacto }
    : { estado: 'pendiente' };
}

/**
 * Entrega el contacto del vendedor y registra la revelación. Solo desde un POST.
 *
 * El registro es lo que alimenta el contador de interés del vendedor y el tope
 * diario, que es la barrera real contra una cuenta que recorra el listado
 * juntando números. Volver al mismo aviso no gasta cupo ni duplica el registro.
 *
 * Si el registro falla no se entrega el teléfono: sin auditoría no hay tope. La
 * excepción es el choque contra el unique de la migración 0018, que significa que
 * la revelación ya estaba registrada (dos envíos a la vez): eso es un éxito.
 */
export async function revelarContacto(
  supabase: SupabaseClient,
  avisoId: number,
  usuarioId: string,
): Promise<ResultadoContacto> {
  const contacto = await telefonoDelVendedor(avisoId);
  if (!contacto) return { estado: 'sin_telefono' };

  if (await yaReveloContacto(supabase, avisoId, usuarioId)) return { estado: 'ok', contacto };

  if (puedeRevelarContacto(await contarRevelacionesHoy(supabase, usuarioId))) return { estado: 'tope' };

  const { error } = await supabase
    .from(TABLA_REVELACIONES)
    .insert({ aviso_id: avisoId, usuario_id: usuarioId });

  if (error && error.code !== '23505') {
    console.error('No se pudo registrar la revelación de contacto:', error.message);
    return { estado: 'error' };
  }

  return { estado: 'ok', contacto };
}

/**
 * Si el usuario ya reportó este aviso, no se registra un segundo reporte: evita
 * que una misma persona infle la bandeja de moderación con denuncias repetidas.
 */
export async function yaReportoAviso(
  supabase: SupabaseClient,
  avisoId: number,
  usuarioId: string,
): Promise<boolean> {
  const total = await contar(
    supabase
      .from('reportes_aviso')
      .select('id', { count: 'exact', head: true })
      .eq('aviso_id', avisoId)
      .eq('usuario_id', usuarioId),
  );
  return total > 0;
}

/**
 * Revelaciones de contacto recibidas por cada aviso del usuario. La política de
 * `contacto_revelaciones` deja leer al dueño del aviso, así que basta el
 * cliente de sesión.
 */
export async function revelacionesPorAviso(
  supabase: SupabaseClient,
  avisoIds: number[],
): Promise<Map<number, number>> {
  const conteo = new Map<number, number>();
  if (!avisoIds.length) return conteo;

  const { data } = await supabase.from(TABLA_REVELACIONES).select('aviso_id').in('aviso_id', avisoIds);
  for (const fila of (data as { aviso_id: number }[]) ?? []) {
    conteo.set(fila.aviso_id, (conteo.get(fila.aviso_id) ?? 0) + 1);
  }
  return conteo;
}

/**
 * Deja como portada la foto de menor `orden` y la copia a `url_imagen`, que es
 * lo que lee `CardAviso` sin saber nada de esta tabla.
 */
export async function sincronizarPortada(supabase: SupabaseClient, avisoId: number): Promise<void> {
  const fotos = await listarFotos(supabase, avisoId);
  await supabase
    .from(TABLA_AVISOS)
    .update({ url_imagen: fotos[0]?.url ?? null })
    .eq('id', avisoId);
}

/**
 * Rutas de todas las fotos del usuario, para vaciar su carpeta del bucket antes
 * de borrar la cuenta: el `ON DELETE CASCADE` arrastra las filas, pero Storage
 * no se entera y los objetos quedarían huérfanos.
 */
export async function rutasDeFotosDelUsuario(
  supabase: SupabaseClient,
  usuarioId: string,
): Promise<string[]> {
  const { data: avisos } = await supabase
    .from(TABLA_AVISOS)
    .select('id')
    .eq('usuario_id', usuarioId);

  const ids = ((avisos as { id: number }[]) ?? []).map((a) => a.id);
  if (!ids.length) return [];

  const { data } = await supabase.from(TABLA_FOTOS).select('ruta').in('aviso_id', ids);
  return ((data as { ruta: string }[]) ?? []).map((f) => f.ruta);
}

/** Ruta del objeto en el bucket: el primer segmento es lo que valida la RLS de Storage. */
export function rutaFoto(usuarioId: string, avisoId: number, extension: string): string {
  return `${usuarioId}/${avisoId}/${crypto.randomUUID()}.${extension}`;
}
