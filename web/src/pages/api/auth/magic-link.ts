import type { APIRoute } from 'astro';
import { rutaInterna, urlEntrar } from '@lib/auth/servidor';

export const prerender = false;

export const POST: APIRoute = async ({ request, url, locals, redirect }) => {
  const datos = await request.formData();
  const volver = rutaInterna(String(datos.get('volver') ?? ''), '/cuenta');

  if (!locals.supabase) return redirect(urlEntrar(volver, 'config'), 303);

  const email = String(datos.get('email') ?? '').trim().toLowerCase();
  if (!email) return redirect(urlEntrar(volver, 'magic-link'), 303);

  const destino = new URL('/api/auth/callback', url.origin);
  destino.searchParams.set('volver', volver);

  const { error } = await locals.supabase.auth.signInWithOtp({
    email,
    // El enlace mágico solo inicia sesión en cuentas existentes; crear cuenta es
    // un acto explícito en /registro, con confirmación de correo.
    options: { emailRedirectTo: destino.href, shouldCreateUser: false },
  });
  if (error) return redirect(urlEntrar(volver, 'magic-link'), 303);

  // Se confirma el envío pase lo que pase con la dirección: decir "esa cuenta no
  // existe" convertiría el formulario en un detector de usuarios registrados.
  return redirect(`${urlEntrar(volver)}&enviado=1`, 303);
};
