import type { APIRoute } from 'astro';
import { rutaInterna, urlEntrar } from '@lib/auth/servidor';

export const prerender = false;

export const POST: APIRoute = async ({ request, locals, redirect }) => {
  const datos = await request.formData();
  const volver = rutaInterna(String(datos.get('volver') ?? ''), '/cuenta');

  if (!locals.supabase) return redirect(urlEntrar(volver, 'config'), 303);

  const email = String(datos.get('email') ?? '').trim().toLowerCase();
  const password = String(datos.get('password') ?? '');

  if (!email || !password) return redirect(urlEntrar(volver, 'credenciales'), 303);

  const { error } = await locals.supabase.auth.signInWithPassword({ email, password });
  if (error) return redirect(urlEntrar(volver, 'credenciales'), 303);

  return redirect(volver, 303);
};
