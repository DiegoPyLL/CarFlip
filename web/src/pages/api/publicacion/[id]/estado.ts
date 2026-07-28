import type { APIRoute } from 'astro';

import { TABLA_AVISOS, obtenerAvisoPropio } from '@lib/publicaciones/consultas';
import { ESTADOS_AVISO, type EstadoAviso } from '@lib/publicaciones/opciones';

export const prerender = false;

export const POST: APIRoute = async ({ params, request, locals, redirect }) => {
  const usuario = locals.usuario;
  const supabase = locals.supabase;
  const id = Number(params.id);
  if (!usuario || !supabase) return redirect('/entrar?volver=/cuenta/avisos', 303);
  if (!Number.isInteger(id)) return redirect('/cuenta/avisos?error=no_encontrado', 303);

  const datos = await request.formData();
  const estado = String(datos.get('estado') ?? '');
  if (!(ESTADOS_AVISO as readonly string[]).includes(estado)) {
    return redirect('/cuenta/avisos?error=datos', 303);
  }

  const aviso = await obtenerAvisoPropio(supabase, id, usuario.id);
  if (!aviso) return redirect('/cuenta/avisos?error=no_encontrado', 303);

  // `disponible` es la lectura genérica del mixin: la web pública no sabe de
  // `estado`, así que ambos deben moverse juntos. Los sincroniza el trigger
  // `particulares_deriva_campos` —junto con `actualizado_en`— para que tampoco
  // puedan desincronizarse desde PostgREST.
  const { error } = await supabase
    .from(TABLA_AVISOS)
    .update({ estado: estado as EstadoAviso })
    .eq('id', id);

  if (error) {
    console.error('No se pudo cambiar el estado:', error.message);
    return redirect('/cuenta/avisos?error=servidor', 303);
  }

  return redirect('/cuenta/avisos?guardado=1', 303);
};
