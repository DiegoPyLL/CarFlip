import type { APIRoute } from 'astro';
import { LARGO_CODIGO, olvidarEmailPendiente } from '@lib/auth/servidor';
import { RE } from '@lib/regex';

export const prerender = false;

/**
 * Canjea el código de recuperación por una sesión y manda a fijar la contraseña.
 *
 * `verifyOtp` no necesita el `code_verifier` que el flujo PKCE deja en una
 * cookie, así que el código sirve igual si el correo se abre en otro dispositivo
 * —el mismo motivo por el que el alta se confirma con código y no con enlace.
 *
 * La sesión que deja acá es recién creada, de modo que el cambio de contraseña
 * que viene a continuación cae dentro de la ventana de 24 horas de Supabase y no
 * vuelve a pedir reautenticación: sin eso, recuperar la cuenta sería imposible.
 */
export const POST: APIRoute = async ({ request, cookies, locals, redirect }) => {
  const datos = await request.formData();

  if (!locals.supabase) return redirect('/recuperar-contrasena?enviado=1&error=config', 303);

  const email = String(datos.get('email') ?? '').trim().toLowerCase();
  const token = String(datos.get('codigo') ?? '').replace(/\D/g, '');

  if (!RE.email.test(email) || token.length !== LARGO_CODIGO) {
    return redirect('/recuperar-contrasena?enviado=1&error=codigo', 303);
  }

  const { error } = await locals.supabase.auth.verifyOtp({ email, token, type: 'recovery' });

  // Un solo mensaje para código erróneo, código expirado y cuenta inexistente:
  // separarlos delataría qué direcciones tienen cuenta.
  if (error) return redirect('/recuperar-contrasena?enviado=1&error=codigo', 303);

  olvidarEmailPendiente(cookies);
  return redirect('/cuenta/seguridad?recuperacion=1', 303);
};
