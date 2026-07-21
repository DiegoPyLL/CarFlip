import type { APIRoute } from 'astro';

import {
  BUCKET_FOTOS,
  TABLA_FOTOS,
  contarFotos,
  listarFotos,
  obtenerAvisoPropio,
  rutaFoto,
  sincronizarPortada,
} from '@lib/publicaciones/consultas';
import { puedeSubirFoto } from '@lib/publicaciones/limites';

export const prerender = false;

const EXTENSION: Record<string, string> = {
  'image/webp': 'webp',
  'image/jpeg': 'jpg',
  'image/png': 'png',
};

export const POST: APIRoute = async ({ params, request, locals, redirect }) => {
  const usuario = locals.usuario;
  const supabase = locals.supabase;
  const id = Number(params.id);
  if (!usuario || !supabase) return redirect('/entrar?volver=/cuenta/avisos', 303);
  if (!Number.isInteger(id)) return redirect('/cuenta/avisos?error=no_encontrado', 303);

  const aviso = await obtenerAvisoPropio(supabase, id, usuario.id);
  if (!aviso) return redirect('/cuenta/avisos?error=no_encontrado', 303);

  const destino = `/cuenta/avisos/${id}/editar`;
  const datos = await request.formData();

  if (String(datos.get('accion')) === 'eliminar') {
    const fotoId = Number(datos.get('foto_id'));
    if (!Number.isInteger(fotoId)) return redirect(`${destino}?error=datos`, 303);

    const foto = (await listarFotos(supabase, id)).find((f) => f.id === fotoId);
    if (!foto) return redirect(`${destino}?error=no_encontrado`, 303);

    const { error: errorBucket } = await supabase.storage.from(BUCKET_FOTOS).remove([foto.ruta]);
    if (errorBucket) console.error('No se pudo borrar la foto del bucket:', errorBucket.message);
    await supabase.from(TABLA_FOTOS).delete().eq('id', fotoId);
    await sincronizarPortada(supabase, id);
    return redirect(`${destino}?guardado=1`, 303);
  }

  const archivos = datos.getAll('foto').filter((f): f is File => f instanceof File && f.size > 0);
  if (!archivos.length) return redirect(`${destino}?error=datos`, 303);

  let existentes = await contarFotos(supabase, id);

  for (const archivo of archivos) {
    const bloqueo = puedeSubirFoto(existentes, archivo.size, archivo.type);
    if (bloqueo) return redirect(`${destino}?error=${bloqueo}`, 303);

    const ruta = rutaFoto(usuario.id, id, EXTENSION[archivo.type]);
    const { error: errorSubida } = await supabase.storage
      .from(BUCKET_FOTOS)
      .upload(ruta, archivo, { contentType: archivo.type });

    if (errorSubida) {
      console.error('No se pudo subir la foto:', errorSubida.message);
      return redirect(`${destino}?error=servidor`, 303);
    }

    const { data: publica } = supabase.storage.from(BUCKET_FOTOS).getPublicUrl(ruta);
    const { error: errorFila } = await supabase.from(TABLA_FOTOS).insert({
      aviso_id: id,
      url: publica.publicUrl,
      ruta,
      orden: existentes,
    });

    if (errorFila) {
      // La fila es la fuente de verdad: sin ella el objeto sería inalcanzable.
      await supabase.storage.from(BUCKET_FOTOS).remove([ruta]);
      console.error('No se pudo registrar la foto:', errorFila.message);
      return redirect(`${destino}?error=servidor`, 303);
    }

    existentes += 1;
  }

  await sincronizarPortada(supabase, id);
  return redirect(`${destino}?guardado=1`, 303);
};
