/**
 * Lectura del catálogo normalizado de marcas, modelos y versiones.
 *
 * Se lee con el cliente de servicio: `catalogo_modelos` y `catalogo_versiones`
 * tienen RLS activa y sin políticas a propósito (migración 0023), porque el
 * catálogo nunca lo consulta el navegador por su cuenta.
 */

import { agruparModelos, type MarcaCatalogo, type VersionCatalogo } from '../catalogo';
import { slugModelo } from '../marcas';
import { supabase } from './client';

export const TABLA_MODELOS = 'catalogo_modelos';
export const TABLA_VERSIONES = 'catalogo_versiones';

/**
 * El catálogo entero, agrupado por marca.
 *
 * Se cachea en el módulo porque cambia cuando corre
 * `scripts/catalogo/cargar_catalogo.py` —no entre peticiones— y lo pide cada
 * carga del formulario de publicación. Un despliegue o un reinicio lo refresca.
 */
let cache: MarcaCatalogo[] | null = null;

export async function obtenerCatalogo(): Promise<MarcaCatalogo[]> {
  if (cache) return cache;

  const { data, error } = await supabase.from(TABLA_MODELOS).select('id, marca, modelo');

  if (error) {
    // Sin catálogo el formulario no puede ofrecer nada; devolver vacío deja que
    // la página lo diga en vez de reventar entera.
    console.error('No se pudo leer el catálogo de modelos:', error.message);
    return [];
  }

  cache = agruparModelos(data ?? []);
  return cache;
}

/**
 * La marca y el modelo canónicos de un id, o `null` si el id no existe.
 *
 * Es lo que convierte el catálogo en normalización de verdad: el formulario
 * manda un id y el aviso se escribe con estas dos cadenas, nunca con texto que
 * venga del cliente.
 */
export async function obtenerModelo(id: number): Promise<{ marca: string; modelo: string } | null> {
  const { data, error } = await supabase
    .from(TABLA_MODELOS)
    .select('marca, modelo')
    .eq('id', id)
    .maybeSingle();

  if (error) {
    console.error('No se pudo leer el modelo del catálogo:', error.message);
    return null;
  }

  return data ?? null;
}

/**
 * El id que le corresponde a un aviso ya publicado, para preseleccionarlo al
 * editar. Busca por slug —no por la grafía— porque los avisos anteriores al
 * catálogo tienen texto libre: "cx 5" y "CX-5" son el mismo modelo. Devuelve
 * `null` si nada calza, y entonces el select queda en el placeholder.
 */
export async function buscarIdModelo(
  marca: string | null,
  modelo: string | null,
): Promise<number | null> {
  if (!marca || !modelo) return null;

  const { data, error } = await supabase
    .from(TABLA_MODELOS)
    .select('id')
    .eq('marca_slug', marca.toLowerCase())
    .eq('modelo_slug', slugModelo(modelo))
    .maybeSingle();

  if (error) {
    console.error('No se pudo buscar el modelo del catálogo:', error.message);
    return null;
  }

  return data?.id ?? null;
}

/** Las versiones de un modelo, en orden alfabético. Lista vacía si no hay. */
export async function obtenerVersiones(modeloId: number): Promise<VersionCatalogo[]> {
  const { data, error } = await supabase
    .from(TABLA_VERSIONES)
    .select('version, combustible, transmision, traccion')
    .eq('modelo_id', modeloId)
    .order('version');

  if (error) {
    console.error('No se pudieron leer las versiones del catálogo:', error.message);
    return [];
  }

  return data ?? [];
}
