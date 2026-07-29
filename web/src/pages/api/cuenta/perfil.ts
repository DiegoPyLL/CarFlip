import type { APIRoute } from 'astro';

import { comunaEnRegion } from '@lib/publicaciones/opciones';
import { RE } from '@lib/regex';
import { normalizar, normalizarTelefonoCL } from '@lib/sanitizar';

export const prerender = false;

export const POST: APIRoute = async ({ request, locals, redirect }) => {
  const usuario = locals.usuario;
  const supabase = locals.supabase;
  if (!usuario || !supabase) return redirect('/entrar?volver=/cuenta', 303);

  const datos = await request.formData();
  const nombre = normalizar(datos.get('nombre'), { max: 100 });
  const telefono = normalizarTelefonoCL(datos.get('telefono'));
  const comuna = String(datos.get('comuna') ?? '').trim();
  const region = String(datos.get('region') ?? '').trim();

  if (!nombre || !RE.nombre.test(nombre) || !telefono) {
    return redirect('/cuenta?error=datos', 303);
  }
  // El par se valida junto: cada parte por separado admitiría "Arica" en la
  // Metropolitana, y el filtro por región de /avisos nunca encontraría el aviso.
  if (!comunaEnRegion(region, comuna)) return redirect('/cuenta?error=datos', 303);

  // El `where` lo impone RLS (`id = auth.uid()`), no este filtro. El `select` es
  // lo que distingue "actualizado" de "no había fila": un UPDATE que no toca
  // ninguna fila vuelve sin error, así que sin él se confirmaba un guardado que
  // nunca ocurrió. La fila la crea el trigger `crear_perfil_al_registrarse`.
  const { data, error } = await supabase
    .from('perfiles')
    .update({ nombre, telefono, region, comuna, actualizado_en: new Date().toISOString() })
    .eq('id', usuario.id)
    .select('id')
    .maybeSingle();

  if (error || !data) {
    console.error('No se pudo guardar el perfil:', error?.message ?? 'sin fila en perfiles');
    return redirect('/cuenta?error=servidor', 303);
  }

  return redirect('/cuenta?guardado=1', 303);
};
