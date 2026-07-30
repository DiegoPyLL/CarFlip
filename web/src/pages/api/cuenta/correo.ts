import type { APIRoute } from 'astro';

import { RUTA_SEGURIDAD } from '@lib/auth/seguridad';
import { RE } from '@lib/regex';

export const prerender = false;

/**
 * Arranca un cambio de correo, y también reenvía los códigos de uno ya en curso.
 *
 * Con "Secure email change" activo, Supabase manda un código a la dirección
 * actual y otro a la nueva, y exige los dos: sin acceso al buzón antiguo nadie
 * se queda con la cuenta, ni siquiera con la sesión robada. Es la razón de que
 * `/cuenta/seguridad` pida dos códigos y no uno.
 *
 * El reenvío no lee la dirección del formulario: la toma de la sesión. Si viniera
 * del POST, cualquiera con la sesión abierta podría redirigir el cambio a un
 * buzón propio en el segundo paso, después de que el usuario ya vio la dirección
 * legítima en pantalla.
 */
export const POST: APIRoute = async ({ request, locals, redirect }) => {
  const usuario = locals.usuario;
  const supabase = locals.supabase;
  if (!usuario || !supabase) return redirect('/entrar?volver=/cuenta/seguridad', 303);

  const datos = await request.formData();
  const reenvio = datos.has('reenviar');
  const email = reenvio
    ? usuario.emailPendiente
    : String(datos.get('email') ?? '').trim().toLowerCase();

  if (reenvio && !email) return redirect(`${RUTA_SEGURIDAD}?error=correo_sin_cambio`, 303);
  if (!RE.email.test(email)) return redirect(`${RUTA_SEGURIDAD}?error=correo_invalido`, 303);
  if (email === usuario.email) return redirect(`${RUTA_SEGURIDAD}?error=correo_igual`, 303);

  const { error } = await supabase.auth.updateUser({ email });

  if (error) {
    // `email_exists` es el único que se puede devolver tal cual: la dirección la
    // escribió quien ya tiene la sesión abierta, así que no revela nada que no
    // pudiera averiguar con el formulario de alta. Aun así el texto es vago.
    if (error.code === 'email_exists') {
      return redirect(`${RUTA_SEGURIDAD}?error=correo_en_uso`, 303);
    }
    console.error('No se pudo iniciar el cambio de correo:', error.message);
    return redirect(`${RUTA_SEGURIDAD}?error=servidor`, 303);
  }

  return redirect(`${RUTA_SEGURIDAD}?estado=correo_enviado`, 303);
};
