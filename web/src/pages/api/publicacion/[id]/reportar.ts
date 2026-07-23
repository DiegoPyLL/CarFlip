import type { APIRoute } from 'astro';

import { rutaInterna } from '@lib/auth/servidor';
import { yaReportoAviso } from '@lib/publicaciones/consultas';
import { MOTIVOS_REPORTE } from '@lib/publicaciones/opciones';
import { normalizar } from '@lib/sanitizar';

export const prerender = false;

export const POST: APIRoute = async ({ params, request, locals, redirect }) => {
  const usuario = locals.usuario;
  const supabase = locals.supabase;
  const id = Number(params.id);

  const datos = await request.formData();
  const volver = rutaInterna(String(datos.get('volver') ?? ''), `/auto/p/${id}`);

  // Reportar exige sesión: si no, cualquiera podría inundar la moderación.
  if (!usuario || !supabase) return redirect(`/entrar?volver=${encodeURIComponent(volver)}`, 303);
  if (!Number.isInteger(id)) return redirect('/?error=no_encontrado', 303);

  const motivo = String(datos.get('motivo') ?? '');
  if (!(MOTIVOS_REPORTE as readonly string[]).includes(motivo)) {
    return redirect(`${volver}?error=datos`, 303);
  }

  // Un mismo usuario no reporta dos veces el mismo aviso: se acusa recibo sin
  // duplicar la denuncia en la bandeja de moderación.
  if (await yaReportoAviso(supabase, id, usuario.id)) {
    return redirect(`${volver}?reportado=1`, 303);
  }

  const { error } = await supabase.from('reportes_aviso').insert({
    aviso_id: id,
    usuario_id: usuario.id,
    motivo,
    detalle: normalizar(datos.get('detalle'), { max: 1000, preservarSaltos: true }) || null,
  });

  if (error) {
    console.error('No se pudo registrar el reporte:', error.message);
    return redirect(`${volver}?error=servidor`, 303);
  }

  return redirect(`${volver}?reportado=1`, 303);
};
