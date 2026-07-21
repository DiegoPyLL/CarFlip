import type { APIRoute } from 'astro';

import {
  TABLA_AVISOS,
  contarAvisosActivos,
  contarCreadosUltimas24h,
  obtenerPerfil,
} from '@lib/publicaciones/consultas';
import { perfilCompleto, puedeCrearAviso } from '@lib/publicaciones/limites';
import { camposDelFormulario } from '@lib/publicaciones/formulario';

export const prerender = false;

const DESTINO = '/cuenta/avisos/nuevo';

export const POST: APIRoute = async ({ request, locals, redirect }) => {
  const usuario = locals.usuario;
  const supabase = locals.supabase;
  if (!usuario || !supabase) return redirect('/entrar?volver=/cuenta/avisos/nuevo', 303);

  if (!usuario.emailConfirmado) return redirect(`${DESTINO}?error=email_sin_confirmar`, 303);

  const perfil = await obtenerPerfil(supabase, usuario.id);
  if (!perfilCompleto(perfil)) return redirect(`${DESTINO}?error=perfil_incompleto`, 303);

  const [activos, creados24h] = await Promise.all([
    contarAvisosActivos(supabase, usuario.id),
    contarCreadosUltimas24h(supabase, usuario.id),
  ]);
  const bloqueo = puedeCrearAviso(activos, creados24h);
  if (bloqueo) return redirect(`${DESTINO}?error=${bloqueo}`, 303);

  const campos = camposDelFormulario(await request.formData());
  if (!campos) return redirect(`${DESTINO}?error=datos`, 303);

  // La URL canónica necesita el id, que solo existe después del insert. Se
  // escribe en un segundo paso; `id_externo` sí se genera aquí para cumplir el
  // unique heredado de ListingMixin.
  const { data, error } = await supabase
    .from(TABLA_AVISOS)
    .insert({
      ...campos,
      usuario_id: usuario.id,
      id_externo: crypto.randomUUID(),
      url: '',
      estado: 'publicado',
      disponible: true,
    })
    .select('id')
    .single();

  if (error || !data) {
    console.error('No se pudo crear la publicación:', error?.message);
    return redirect(`${DESTINO}?error=servidor`, 303);
  }

  const sitio = import.meta.env.SITE ?? 'https://carflip.cl';
  await supabase
    .from(TABLA_AVISOS)
    .update({ url: new URL(`/auto/p/${data.id}`, sitio).href })
    .eq('id', data.id);

  // A editar: es donde se suben las fotos, y un aviso sin foto rinde mal.
  return redirect(`/cuenta/avisos/${data.id}/editar?creado=1`, 303);
};
