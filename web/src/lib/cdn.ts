const CDN_BASE = (import.meta.env.CDN_BASE_URL ?? '').replace(/\/$/, '');

/** Antepone el dominio del CDN a las claves de objeto; deja pasar las URL absolutas. */
export function resolverUrlImagen(url: string | null): string | null {
  if (!url) return null;
  if (!CDN_BASE || url.startsWith('http')) return url;
  return `${CDN_BASE}/${url.replace(/^\//, '')}`;
}
