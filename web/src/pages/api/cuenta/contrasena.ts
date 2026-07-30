import type { APIRoute } from 'astro';

import { LARGO_CODIGO, LARGO_MINIMO_CLAVE } from '@lib/auth/servidor';
import { RUTA_SEGURIDAD } from '@lib/auth/seguridad';

export const prerender = false;

/**
 * Fija una contraseña nueva, sea por cambio voluntario o como último paso de la
 * recuperación.
 *
 * El campo de confirmación bloquea pegar en el cliente para forzar a retipear la
 * clave, pero esa barrera es solo UX: quien apague JS o edite el POST la evita,
 * así que acá se revalida igual, como ya hace `auth/registro.ts`.
 *
 * El `nonce` es el código de `reauthenticate()`. Solo viaja cuando el servidor lo
 * pidió: con "Secure password change" activo, Supabase lo exige únicamente si la
 * sesión tiene más de 24 horas, así que quien acaba de entrar —o de recuperar la
 * cuenta, que también estrena sesión— no paga ninguna fricción.
 */
export const POST: APIRoute = async ({ request, locals, redirect }) => {
  const usuario = locals.usuario;
  const supabase = locals.supabase;
  if (!usuario || !supabase) return redirect('/entrar?volver=/cuenta/seguridad', 303);

  const datos = await request.formData();
  const password = String(datos.get('password') ?? '');
  const confirmacion = String(datos.get('password_confirmacion') ?? '');
  const nonce = String(datos.get('nonce') ?? '').replace(/\D/g, '');

  if (password.length < LARGO_MINIMO_CLAVE) {
    return redirect(`${RUTA_SEGURIDAD}?error=clave_corta`, 303);
  }
  if (password !== confirmacion) {
    return redirect(`${RUTA_SEGURIDAD}?error=clave_distinta`, 303);
  }

  const { error } = await supabase.auth.updateUser(
    nonce.length === LARGO_CODIGO ? { password, nonce } : { password },
  );

  if (error) {
    // Los tres primeros son respuestas legítimas al dato que se acaba de tipear
    // y el usuario puede corregirlos; el resto es un fallo nuestro y va al log.
    // Supabase avisa que hace falta reautenticar, pero no manda el código: hay
    // que pedirlo. Sin esto la página prometía un correo que nunca salía.
    if (error.code === 'reauthentication_needed') {
      const envio = await supabase.auth.reauthenticate();
      if (envio.error) {
        console.error('Código de reautenticación no enviado:', envio.error.message);
        return redirect(`${RUTA_SEGURIDAD}?error=servidor`, 303);
      }
      return redirect(`${RUTA_SEGURIDAD}?error=reautenticar`, 303);
    }
    if (error.code === 'reauthentication_not_valid' || error.code === 'reauth_nonce_missing') {
      return redirect(`${RUTA_SEGURIDAD}?error=nonce_invalido`, 303);
    }
    if (error.code === 'same_password') {
      return redirect(`${RUTA_SEGURIDAD}?error=clave_repetida`, 303);
    }
    if (error.code === 'weak_password') {
      return redirect(`${RUTA_SEGURIDAD}?error=clave_debil`, 303);
    }
    console.error('No se pudo cambiar la contraseña:', error.message);
    return redirect(`${RUTA_SEGURIDAD}?error=servidor`, 303);
  }

  return redirect(`${RUTA_SEGURIDAD}?estado=contrasena_guardada`, 303);
};
