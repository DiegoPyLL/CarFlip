import type { APIRoute } from 'astro';

export const prerender = false;

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const LARGO_MINIMO_CLAVE = 8;

export const POST: APIRoute = async ({ request, url, locals, redirect }) => {
  const datos = await request.formData();

  // Honeypot, igual que en /contacto: invisible para personas, un bot lo llena.
  if (String(datos.get('web') ?? '').length > 0) return redirect('/registro?enviado=1', 303);

  if (!locals.supabase) return redirect('/registro?error=config', 303);

  const email = String(datos.get('email') ?? '').trim().toLowerCase();
  const password = String(datos.get('password') ?? '');

  if (!EMAIL_RE.test(email) || password.length < LARGO_MINIMO_CLAVE) {
    return redirect('/registro?error=1', 303);
  }

  const { error } = await locals.supabase.auth.signUp({
    email,
    password,
    options: { emailRedirectTo: new URL('/api/auth/callback?volver=/cuenta', url.origin).href },
  });
  if (error) return redirect('/registro?error=1', 303);

  return redirect('/registro?enviado=1', 303);
};
