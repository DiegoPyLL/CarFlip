import type { APIRoute } from 'astro';

import { revelarContacto } from '@lib/publicaciones/consultas';

export const prerender = false;

/**
 * Revela el contacto del vendedor de un aviso y lo registra.
 *
 * Es un POST porque consume el cupo diario del usuario: `security.checkOrigin` de
 * Astro protege las escrituras que llegan por formulario, y no cubre GET. Cuando
 * la revelación se hacía durante el render de `/auto/p/[id]`, un sitio externo
 * podía agotarle las 25 del día a cualquiera con sesión con solo mandarlo a
 * navegar de un aviso a otro.
 *
 * El error viaja como código en la querystring y la página lo traduce contra
 * `MENSAJE_ERROR`: nadie puede inyectar un texto por URL.
 */
export const POST: APIRoute = async ({ params, locals, redirect }) => {
  const usuario = locals.usuario;
  const supabase = locals.supabase;
  const id = Number(params.id);

  if (!Number.isInteger(id)) return redirect('/?error=no_encontrado', 303);

  const destino = `/auto/p/${id}`;
  if (!usuario || !supabase) {
    return redirect(`/entrar?volver=${encodeURIComponent(destino)}`, 303);
  }

  const revelacion = await revelarContacto(supabase, id, usuario.id);
  if (revelacion.estado === 'tope') return redirect(`${destino}?error=tope_revelaciones`, 303);
  if (revelacion.estado === 'error') return redirect(`${destino}?error=servidor`, 303);

  return redirect(`${destino}#contacto`, 303);
};
