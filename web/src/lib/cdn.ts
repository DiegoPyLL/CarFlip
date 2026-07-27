const CDN_BASE = (import.meta.env.CDN_BASE_URL ?? '').replace(/\/$/, '');

function origen(url: string): string | null {
  try {
    return new URL(url).origin;
  } catch {
    return null;
  }
}

/**
 * Orígenes de los que el sitio sirve imágenes: R2 para las fotos convertidas por
 * el pipeline y el Storage de Supabase para las que sube un particular. Es la
 * lista que consume el `img-src` de la CSP en `middleware.ts`, para que la
 * política y lo que la página realmente pinta no puedan divergir.
 */
export const ORIGENES_IMAGEN = [
  origen(CDN_BASE),
  origen((import.meta.env.PUBLIC_SUPABASE_URL as string) ?? ''),
].filter((o): o is string => o !== null);

/**
 * URL final de una imagen: antepone el dominio del CDN a las claves de objeto y
 * deja pasar las URL absolutas de los orígenes permitidos.
 *
 * Una URL absoluta de cualquier otro host devuelve `null` —y la vista pinta su
 * placeholder— en vez de una imagen que la CSP bloquearía dejando el hueco. Pasa
 * con las filas viejas cuya subida a R2 falló y quedaron apuntando al portal de
 * origen, y con cualquier fila que se hubiera insertado directo por PostgREST
 * apuntando a un pixel externo.
 */
export function resolverUrlImagen(url: string | null): string | null {
  if (!url) return null;
  if (!/^https?:\/\//i.test(url)) {
    return CDN_BASE ? `${CDN_BASE}/${url.replace(/^\//, '')}` : url;
  }
  const suyo = origen(url);
  return suyo && ORIGENES_IMAGEN.includes(suyo) ? url : null;
}
