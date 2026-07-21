import type { APIRoute } from 'astro';

import { REGIONES } from '@lib/publicaciones/opciones';
import { normalizar, normalizarTelefonoCL } from '@lib/sanitizar';

export const prerender = false;

// Mismo criterio que /contacto: letras de cualquier idioma y espacios.
const NOMBRE_RE = /^[\p{L}\s]+$/u;

export const POST: APIRoute = async ({ request, locals, redirect }) => {
  const usuario = locals.usuario;
  const supabase = locals.supabase;
  if (!usuario || !supabase) return redirect('/entrar?volver=/cuenta', 303);

  const datos = await request.formData();
  const nombre = normalizar(datos.get('nombre'), { max: 100 });
  const telefono = normalizarTelefonoCL(datos.get('telefono'));
  const comuna = normalizar(datos.get('comuna'), { max: 100 });
  const region = String(datos.get('region') ?? '');

  if (!nombre || !NOMBRE_RE.test(nombre) || !telefono || !comuna) {
    return redirect('/cuenta?error=datos', 303);
  }
  if (!(REGIONES as readonly string[]).includes(region)) return redirect('/cuenta?error=datos', 303);

  // El `where` lo impone RLS (`id = auth.uid()`), no este filtro.
  const { error } = await supabase
    .from('perfiles')
    .update({ nombre, telefono, region, comuna, actualizado_en: new Date().toISOString() })
    .eq('id', usuario.id);

  if (error) {
    console.error('No se pudo guardar el perfil:', error.message);
    return redirect('/cuenta?error=servidor', 303);
  }

  return redirect('/cuenta?guardado=1', 303);
};
