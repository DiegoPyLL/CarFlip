import type { APIRoute } from 'astro';
import { guardarEmailPendiente } from '@lib/auth/servidor';
import { RE } from '@lib/regex';

export const prerender = false;

/**
 * Pide el código de recuperación, y también lo reenvía: el segundo botón de
 * `/recuperar-contrasena` apunta acá mismo, porque para Supabase las dos cosas
 * son la misma llamada.
 *
 * `resetPasswordForEmail` va sin `redirectTo` a propósito: la plantilla de
 * "Reset password" muestra `{{ .Token }}` y no el enlace. El enlace iría por
 * PKCE —atado al navegador que lo pidió, como ya explica `registro.ts`— y encima
 * los escáneres de correo corporativo lo abren antes que el usuario y queman el
 * token de un solo uso.
 */
export const POST: APIRoute = async ({ request, cookies, locals, redirect }) => {
  const datos = await request.formData();
  const reenvio = datos.has('reenviar');
  const destino = `/recuperar-contrasena?enviado=1${reenvio ? '&reenviado=1' : ''}`;

  if (!locals.supabase) return redirect('/recuperar-contrasena?error=config', 303);

  const email = String(datos.get('email') ?? '').trim().toLowerCase();
  if (!RE.email.test(email)) return redirect('/recuperar-contrasena?error=email', 303);

  const { error } = await locals.supabase.auth.resetPasswordForEmail(email);

  // La respuesta es la misma exista o no la cuenta: propagar el error convertiría
  // este formulario en un detector de usuarios, el mismo criterio que siguen el
  // enlace mágico y el reenvío del código de alta. Queda en el log.
  if (error) console.error('Código de recuperación no enviado:', error.message);

  guardarEmailPendiente(cookies, email);
  return redirect(destino, 303);
};
