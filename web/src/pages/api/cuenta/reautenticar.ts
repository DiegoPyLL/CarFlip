import type { APIRoute } from 'astro';

import { RUTA_SEGURIDAD } from '@lib/auth/seguridad';

export const prerender = false;

/**
 * Pide el código de reautenticación al correo de la cuenta.
 *
 * Es la única salida soportada de `reauthenticate()`: su código se consume como
 * `nonce` de `updateUser()`, y no hay forma de exigirlo antes de otras
 * operaciones. Por eso el blindaje llega hasta el cambio de contraseña y el
 * borrado de cuenta sigue apoyado en escribir ELIMINAR.
 */
export const POST: APIRoute = async ({ locals, redirect }) => {
  const usuario = locals.usuario;
  const supabase = locals.supabase;
  if (!usuario || !supabase) return redirect('/entrar?volver=/cuenta/seguridad', 303);

  const { error } = await supabase.auth.reauthenticate();

  if (error) {
    console.error('Código de reautenticación no enviado:', error.message);
    return redirect(`${RUTA_SEGURIDAD}?error=servidor`, 303);
  }

  return redirect(`${RUTA_SEGURIDAD}?estado=nonce_enviado`, 303);
};
