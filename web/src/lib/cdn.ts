const CDN_BASE = (import.meta.env.CDN_BASE_URL ?? '').replace(/\/$/, '');

/** Convierte URL S3 o clave de objeto a URL CloudFront cuando CDN_BASE_URL está definida. */
export function resolverUrlImagen(url: string | null): string | null {
  if (!url) return null;
  if (!CDN_BASE) return url;
  if (url.startsWith(CDN_BASE)) return url;
  if (url.startsWith('autocosmos/') || url.startsWith('yapo/')) {
    return `${CDN_BASE}/${url}`;
  }
  const desdeS3 = url.match(/carflipbucket\.s3\.[^/]+\.amazonaws\.com\/(.+)/);
  if (desdeS3) return `${CDN_BASE}/${desdeS3[1]}`;
  return url;
}
