import type { APIRoute } from 'astro';

import {
  BUCKET_FOTOS,
  TABLA_AVISOS,
  listarFotos,
  obtenerAvisoPropio,
} from '@lib/publicaciones/consultas';
import { camposDelFormulario } from '@lib/publicaciones/formulario';

export const prerender = false;

export const POST: APIRoute = async ({ params, request, locals, redirect }) => {
  const usuario = locals.usuario;
  const supabase = locals.supabase;
  const id = Number(params.id);
  if (!usuario || !supabase) return redirect('/entrar?volver=/cuenta/avisos', 303);
  if (!Number.isInteger(id)) return redirect('/cuenta/avisos?error=no_encontrado', 303);

  const aviso = await obtenerAvisoPropio(supabase, id, usuario.id);
  if (!aviso) return redirect('/cuenta/avisos?error=no_encontrado', 303);

  const datos = await request.formData();
  const destino = `/cuenta/avisos/${id}/editar`;

  if (String(datos.get('accion')) === 'eliminar') {
    // Primero los objetos del bucket: si se borra la fila antes, se pierden las
    // rutas y quedarían archivos huérfanos ocupando espacio para siempre.
    const fotos = await listarFotos(supabase, id);
    if (fotos.length) {
      const { error: errorBucket } = await supabase.storage
        .from(BUCKET_FOTOS)
        .remove(fotos.map((f) => f.ruta));
      // No aborta el borrado del aviso, pero tiene que quedar registrado: un
      // fallo silencioso aquí deja archivos huérfanos ocupando espacio.
      if (errorBucket) console.error('No se pudieron borrar las fotos del bucket:', errorBucket.message);
    }
    const { error } = await supabase.from(TABLA_AVISOS).delete().eq('id', id);
    if (error) {
      console.error('No se pudo eliminar la publicación:', error.message);
      return redirect(`${destino}?error=servidor`, 303);
    }
    return redirect('/cuenta/avisos?eliminado=1', 303);
  }

  const campos = camposDelFormulario(datos);
  if (!campos) return redirect(`${destino}?error=datos`, 303);

  // Una bajada de precio alimenta `precio_anterior`/`delta_pct`, que es lo que
  // lee signosDelta() para mostrar "▼ n%" sin ningún caso especial por fuente.
  const anterior = aviso.precio;
  const bajada = anterior !== null && campos.precio < anterior;

  const { error } = await supabase
    .from(TABLA_AVISOS)
    .update({
      ...campos,
      ...(bajada
        ? {
            precio_anterior: anterior,
            delta_pct: ((campos.precio - anterior) / anterior) * 100,
          }
        : {}),
      actualizado_en: new Date().toISOString(),
      ultima_vez_visto: new Date().toISOString(),
    })
    .eq('id', id);

  if (error) {
    console.error('No se pudo actualizar la publicación:', error.message);
    return redirect(`${destino}?error=servidor`, 303);
  }

  return redirect(`${destino}?guardado=1`, 303);
};
