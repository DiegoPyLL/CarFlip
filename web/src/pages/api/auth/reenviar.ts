import type { APIRoute } from 'astro';
import { guardarEmailPendiente } from '@lib/auth/servidor';
import { EMAIL_RE } from '@lib/sanitizar';

export const prerender = false;

// Reenvía el código de confirmación cuando el primer correo no llegó o expiró.
export const POST: APIRoute = async ({ request, cookies, locals, redirect }) => {
  const datos = await request.formData();

  if (!locals.supabase) return redirect('/registro?enviado=1&error=config', 303);

  const email = String(datos.get('email') ?? '').trim().toLowerCase();
  if (!EMAIL_RE.test(email)) return redirect('/registro?enviado=1&error=codigo', 303);

  const { error } = await locals.supabase.auth.resend({ type: 'signup', email });

  // La respuesta es la misma exista o no la cuenta, y esté o no confirmada:
  // propagar el error diría quién está registrado. Queda en el log.
  if (error) console.error('Código de confirmación no reenviado:', error.message);

  guardarEmailPendiente(cookies, email);
  return redirect('/registro?enviado=1&reenviado=1', 303);
};
