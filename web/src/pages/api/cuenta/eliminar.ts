import type { APIRoute } from 'astro';

import { supabase as servicio } from '@lib/db/client';
import { BUCKET_FOTOS, rutasDeFotosDelUsuario } from '@lib/publicaciones/consultas';
import { confirmacionValida } from '@lib/publicaciones/limites';

export const prerender = false;

/**
 * Borra la cuenta y todo lo que cuelga de ella (Ley 21.719, derecho de
 * supresión). La fila de `auth.users` es la raíz: el `ON DELETE CASCADE` de
 * `perfiles` arrastra avisos, fotos, revelaciones y reportes.
 *
 * Es la única escritura de la cuenta que no puede ir con el cliente de sesión:
 * eliminar un usuario de `auth` solo lo permite la API de administración, que
 * exige la service key. El id nunca viene del formulario, siempre de la sesión
 * ya validada por el middleware.
 */
export const POST: APIRoute = async ({ request, locals, redirect }) => {
  const usuario = locals.usuario;
  const supabase = locals.supabase;
  if (!usuario || !supabase) return redirect('/entrar?volver=/cuenta', 303);

  const datos = await request.formData();
  if (!confirmacionValida(String(datos.get('confirmacion') ?? ''))) {
    return redirect('/cuenta?error=confirmacion', 303);
  }

  // Primero el bucket: después del borrado ya no habría forma de saber qué
  // objetos eran suyos, y quedarían ocupando espacio para siempre.
  const rutas = await rutasDeFotosDelUsuario(supabase, usuario.id);
  if (rutas.length) {
    const { error } = await supabase.storage.from(BUCKET_FOTOS).remove(rutas);
    if (error) console.error('No se pudieron borrar las fotos de la cuenta:', error.message);
  }

  const { error } = await servicio.auth.admin.deleteUser(usuario.id);
  if (error) {
    console.error('No se pudo eliminar la cuenta:', error.message);
    return redirect('/cuenta?error=servidor', 303);
  }

  // `local` solo limpia las cookies: el token ya no sirve contra el servidor.
  await supabase.auth.signOut({ scope: 'local' });
  // El destino es /entrar y no `/`: la home redirige 301 cualquier querystring
  // a /avisos, así que el acuse de recibo se perdería por el camino.
  return redirect('/entrar?eliminada=1', 303);
};
