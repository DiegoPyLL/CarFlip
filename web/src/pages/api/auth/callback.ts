import type { APIRoute } from 'astro';
import { rutaInterna, urlEntrar } from '@lib/auth/servidor';

export const prerender = false;

// Vuelta del enlace mágico y de Google OAuth: cambia el `code` por una sesión y
// deja las cookies puestas antes de devolver al usuario a donde estaba.
export const GET: APIRoute = async ({ url, locals, redirect }) => {
  const volver = rutaInterna(url.searchParams.get('volver'), '/cuenta');

  if (!locals.supabase) return redirect(urlEntrar(volver, 'config'), 303);

  const code = url.searchParams.get('code');
  if (!code) return redirect(urlEntrar(volver, 'sesion'), 303);

  const { error } = await locals.supabase.auth.exchangeCodeForSession(code);
  if (error) return redirect(urlEntrar(volver, 'sesion'), 303);

  return redirect(volver, 303);
};
