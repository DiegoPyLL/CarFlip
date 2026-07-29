import type { APIRoute } from 'astro';
import { guardarEmailPendiente } from '@lib/auth/servidor';
import { EMAIL_RE } from '@lib/sanitizar';

export const prerender = false;

const LARGO_MINIMO_CLAVE = 8;

// La cuenta se confirma con el código de ocho dígitos que Supabase envía por
// correo, no con un enlace: el enlace usa el flujo PKCE, que ata la confirmación
// al navegador donde se envió este formulario y deja fuera a quien abra el correo
// en otro dispositivo. Por eso el `signUp` de más abajo no lleva `emailRedirectTo`.
export const POST: APIRoute = async ({ request, cookies, locals, redirect }) => {
  const datos = await request.formData();

  // Honeypot, igual que en /contacto: invisible para personas, un bot lo llena.
  if (String(datos.get('web') ?? '').length > 0) return redirect('/registro?enviado=1', 303);

  if (!locals.supabase) return redirect('/registro?error=config', 303);

  const email = String(datos.get('email') ?? '').trim().toLowerCase();
  const password = String(datos.get('password') ?? '');
  const passwordConfirmacion = String(datos.get('password_confirmacion') ?? '');

  // El campo de confirmación bloquea pegar en el cliente para forzar a
  // retipear la clave, pero esa barrera es solo UX: quien apague JS o edite
  // el POST directamente la evita, así que el servidor revalida igual.
  if (
    !EMAIL_RE.test(email) ||
    password.length < LARGO_MINIMO_CLAVE ||
    password !== passwordConfirmacion
  ) {
    return redirect('/registro?error=1', 303);
  }

  const { error } = await locals.supabase.auth.signUp({ email, password });
  if (error) return redirect('/registro?error=1', 303);

  guardarEmailPendiente(cookies, email);
  return redirect('/registro?enviado=1', 303);
};
