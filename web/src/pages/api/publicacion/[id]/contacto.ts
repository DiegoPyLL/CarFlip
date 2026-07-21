import type { APIRoute } from 'astro';

import { rutaInterna, urlEntrar } from '@lib/auth/servidor';
import {
  TABLA_REVELACIONES,
  contarRevelacionesHoy,
  telefonoDelVendedor,
  yaReveloContacto,
} from '@lib/publicaciones/consultas';
import { puedeRevelarContacto } from '@lib/publicaciones/limites';

export const prerender = false;

/**
 * Registra la revelación del contacto y devuelve al aviso, que ya renderiza el
 * teléfono en el servidor para quien lo reveló. Es un POST y no un GET porque
 * escribe: ni un prefetch ni un rastreador deben consumir cupo.
 *
 * Así el flujo entero funciona sin JS ni fetch, y el número nunca viaja en el
 * HTML público.
 */
export const POST: APIRoute = async ({ params, request, locals, redirect }) => {
  const usuario = locals.usuario;
  const supabase = locals.supabase;
  const id = Number(params.id);

  const datos = await request.formData();
  const volver = rutaInterna(String(datos.get('volver') ?? ''), `/auto/p/${id}`);
  const destino = (error?: string) => `${volver}${error ? `?error=${error}` : ''}#contacto`;

  if (!usuario || !supabase) return redirect(urlEntrar(volver), 303);
  if (!Number.isInteger(id)) return redirect('/?error=no_encontrado', 303);

  // Revelar dos veces el mismo aviso no gasta cupo ni duplica la auditoría.
  if (await yaReveloContacto(supabase, id, usuario.id)) return redirect(destino(), 303);

  const bloqueo = puedeRevelarContacto(await contarRevelacionesHoy(supabase, usuario.id));
  if (bloqueo) return redirect(destino(bloqueo), 303);

  // Se comprueba antes de registrar: sin teléfono no hay nada que revelar.
  if (!(await telefonoDelVendedor(id))) return redirect(destino('no_encontrado'), 303);

  const { error } = await supabase
    .from(TABLA_REVELACIONES)
    .insert({ aviso_id: id, usuario_id: usuario.id });

  if (error) {
    // Sin registro no hay auditoría ni tope: es preferible no entregar el dato.
    console.error('No se pudo registrar la revelación de contacto:', error.message);
    return redirect(destino('servidor'), 303);
  }

  return redirect(destino(), 303);
};
