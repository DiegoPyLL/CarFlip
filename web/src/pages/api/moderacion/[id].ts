import type { APIRoute } from 'astro';

import {
  avisoDelReporte,
  cerrarReportes,
  despublicarAviso,
} from '@lib/publicaciones/moderacion';

export const prerender = false;

const DESTINO = '/dashboard#reportes';

/**
 * Resuelve un reporte: `despublicar` retira el aviso y da por atendidos todos
 * sus reportes; `descartar` los cierra sin tocarlo.
 *
 * Las dos acciones se deciden sobre el aviso, no sobre el reporte suelto: si un
 * mismo aviso acumula varias denuncias, revisarlo una vez las responde todas.
 */
export const POST: APIRoute = async ({ params, request, locals, redirect }) => {
  const usuario = locals.usuario;
  const supabase = locals.supabase;
  const id = Number(params.id);

  // El middleware ya cierra /api/moderacion a quien no sea administrador. Se
  // repite aquí porque esta ruta escribe sobre avisos de otras personas.
  if (!usuario || !supabase || usuario.rol !== 'admin') return redirect('/', 303);
  if (!Number.isInteger(id)) return redirect(`${DESTINO}?error=no_encontrado`, 303);

  const datos = await request.formData();
  const accion = String(datos.get('accion') ?? '');
  if (accion !== 'despublicar' && accion !== 'descartar') {
    return redirect(`${DESTINO}?error=datos`, 303);
  }

  const avisoId = await avisoDelReporte(supabase, id);
  if (avisoId === null) return redirect(`${DESTINO}?error=no_encontrado`, 303);

  if (accion === 'despublicar' && !(await despublicarAviso(supabase, avisoId))) {
    return redirect(`${DESTINO}?error=servidor`, 303);
  }

  const cerrado = await cerrarReportes(
    supabase,
    avisoId,
    accion === 'despublicar' ? 'resuelto' : 'descartado',
  );
  if (!cerrado) return redirect(`${DESTINO}?error=servidor`, 303);

  return redirect(`${DESTINO}?moderado=${accion}`, 303);
};
