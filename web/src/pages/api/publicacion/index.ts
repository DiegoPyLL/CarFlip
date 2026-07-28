import type { APIRoute } from 'astro';

import { TABLA_AVISOS, contarCreadosUltimas24h, obtenerPerfil } from '@lib/publicaciones/consultas';
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

  const creados24h = await contarCreadosUltimas24h(supabase, usuario.id);
  const bloqueo = puedeCrearAviso(creados24h);
  if (bloqueo) return redirect(`${DESTINO}?error=${bloqueo}`, 303);

  const campos = camposDelFormulario(await request.formData());
  if (!campos) return redirect(`${DESTINO}?error=datos`, 303);

  // `titulo`, `url` y `disponible` los deriva la base (trigger
  // `particulares_deriva_campos`): la URL canónica necesita el id, que no existe
  // hasta el insert, y así se ahorra el segundo UPDATE que hacía falta para
  // escribirla. `id_externo` sí se genera aquí, para cumplir el unique heredado
  // de ListingMixin.
  const { data, error } = await supabase
    .from(TABLA_AVISOS)
    .insert({ ...campos, usuario_id: usuario.id, id_externo: crypto.randomUUID(), estado: 'publicado' })
    .select('id')
    .single();

  if (error || !data) {
    console.error('No se pudo crear la publicación:', error?.message);
    return redirect(`${DESTINO}?error=servidor`, 303);
  }

  // A editar: es donde se suben las fotos, y un aviso sin foto rinde mal.
  return redirect(`/cuenta/avisos/${data.id}/editar?creado=1`, 303);
};
