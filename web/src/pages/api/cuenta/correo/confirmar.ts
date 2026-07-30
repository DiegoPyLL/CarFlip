import type { APIRoute } from 'astro';

import { LARGO_CODIGO } from '@lib/auth/servidor';
import { RUTA_SEGURIDAD } from '@lib/auth/seguridad';

export const prerender = false;

/** Los dígitos del campo, sin separadores; vacío si no tiene el largo exacto. */
function codigoValido(valor: FormDataEntryValue | null): string {
  const digitos = String(valor ?? '').replace(/\D/g, '');
  return digitos.length === LARGO_CODIGO ? digitos : '';
}

/**
 * Cierra el cambio de correo con los dos códigos de la confirmación doble.
 *
 * Las dos direcciones salen de la sesión —`usuario.email` y `usuario.emailPendiente`,
 * que el middleware toma del `new_email` de Supabase— y nunca del formulario, que
 * solo aporta los códigos. Es el mismo criterio de `cuenta/eliminar.ts`, donde el
 * id del usuario tampoco viene del POST: si la dirección viajara en un campo, se
 * podría cambiar entre que la página se dibuja y el formulario se envía.
 *
 * Los dos códigos se comprueban de forma antes de canjear ninguno: cada token es
 * de un solo uso, así que canjear el primero y descubrir después que el segundo
 * venía vacío dejaba el cambio a medias y sin salida.
 */
export const POST: APIRoute = async ({ request, locals, redirect }) => {
  const usuario = locals.usuario;
  const supabase = locals.supabase;
  if (!usuario || !supabase) return redirect('/entrar?volver=/cuenta/seguridad', 303);

  const nuevo = usuario.emailPendiente;
  if (!nuevo) return redirect(`${RUTA_SEGURIDAD}?error=correo_sin_cambio`, 303);

  const datos = await request.formData();
  const codigoActual = codigoValido(datos.get('codigo_actual'));
  const codigoNuevo = codigoValido(datos.get('codigo_nuevo'));

  if (!codigoActual || !codigoNuevo) {
    return redirect(`${RUTA_SEGURIDAD}?error=correo_codigo`, 303);
  }

  // El orden importa: Supabase da por cerrado el cambio al canjear el segundo,
  // así que la dirección nueva va al final.
  const canjes = [
    { email: usuario.email, token: codigoActual },
    { email: nuevo, token: codigoNuevo },
  ];

  for (const { email, token } of canjes) {
    const { error } = await supabase.auth.verifyOtp({ email, token, type: 'email_change' });
    if (error) {
      console.error('Cambio de correo no confirmado:', error.message);
      return redirect(`${RUTA_SEGURIDAD}?error=correo_codigo`, 303);
    }
  }

  return redirect(`${RUTA_SEGURIDAD}?estado=correo_guardado`, 303);
};
