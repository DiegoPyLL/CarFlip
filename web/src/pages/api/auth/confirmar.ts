import type { APIRoute } from 'astro';
import { LARGO_CODIGO, olvidarEmailPendiente } from '@lib/auth/servidor';
import { RE } from '@lib/regex';

export const prerender = false;

// Confirma la cuenta con el código de ocho dígitos del correo. A diferencia del
// enlace, `verifyOtp` no necesita el `code_verifier` que el flujo PKCE deja en
// una cookie, así que funciona igual en otro navegador o en otro dispositivo.
export const POST: APIRoute = async ({ request, cookies, locals, redirect }) => {
  const datos = await request.formData();

  if (!locals.supabase) return redirect('/registro?enviado=1&error=config', 303);

  const email = String(datos.get('email') ?? '').trim().toLowerCase();
  const token = String(datos.get('codigo') ?? '').replace(/\D/g, '');

  if (!RE.email.test(email) || token.length !== LARGO_CODIGO) {
    return redirect('/registro?enviado=1&error=codigo', 303);
  }

  const { error } = await locals.supabase.auth.verifyOtp({ email, token, type: 'signup' });

  // Un solo mensaje para código erróneo, código expirado y cuenta inexistente:
  // separarlos convertiría este formulario en un detector de cuentas, el mismo
  // criterio que sigue el enlace mágico.
  if (error) return redirect('/registro?enviado=1&error=codigo', 303);

  // La sesión ya viaja en las cookies que puso `verifyOtp`; el correo pendiente
  // dejó de serlo.
  olvidarEmailPendiente(cookies);
  return redirect('/cuenta', 303);
};
