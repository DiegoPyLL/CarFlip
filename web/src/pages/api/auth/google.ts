import type { APIRoute } from 'astro';
import { rutaInterna, urlEntrar } from '@lib/auth/servidor';

export const prerender = false;

export const GET: APIRoute = async ({ url, locals, redirect }) => {
  const volver = rutaInterna(url.searchParams.get('volver'), '/cuenta');

  if (!locals.supabase) return redirect(urlEntrar(volver, 'config'), 303);

  const destino = new URL('/api/auth/callback', url.origin);
  destino.searchParams.set('volver', volver);

  const { data, error } = await locals.supabase.auth.signInWithOAuth({
    provider: 'google',
    options: { redirectTo: destino.href },
  });
  if (error || !data.url) return redirect(urlEntrar(volver, 'google'), 303);

  return redirect(data.url, 302);
};
