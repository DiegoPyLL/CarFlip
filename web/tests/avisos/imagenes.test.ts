import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

/**
 * `img-src` de la CSP solo admite los orígenes desde los que el sitio sirve
 * fotos, así que `resolverUrlImagen` tiene que descartar cualquier otro: si
 * devolviera la URL, el navegador la bloquearía y la tarjeta quedaría con el
 * hueco en vez de su placeholder. Pasa con las filas viejas cuya subida a R2
 * falló y con las que se hubieran insertado directo por PostgREST apuntando a un
 * pixel externo.
 */

const CDN = 'https://img.carflip.cl';
const SUPABASE = 'https://proyecto.supabase.co';

async function importarCdn() {
  vi.resetModules();
  return import('@lib/cdn');
}

beforeEach(() => {
  vi.stubEnv('CDN_BASE_URL', CDN);
  vi.stubEnv('PUBLIC_SUPABASE_URL', SUPABASE);
});

afterEach(() => {
  vi.unstubAllEnvs();
});

describe('ORIGENES_IMAGEN', () => {
  it('son los orígenes de R2 y del Storage de Supabase, sin rutas', async () => {
    const { ORIGENES_IMAGEN } = await importarCdn();
    expect(ORIGENES_IMAGEN).toEqual([CDN, SUPABASE]);
  });

  it('omite lo que no esté configurado, en vez de dejar una entrada vacía', async () => {
    vi.stubEnv('CDN_BASE_URL', '');
    const { ORIGENES_IMAGEN } = await importarCdn();
    expect(ORIGENES_IMAGEN).toEqual([SUPABASE]);
  });
});

describe('resolverUrlImagen', () => {
  it('antepone el CDN a las claves de objeto', async () => {
    const { resolverUrlImagen } = await importarCdn();
    expect(resolverUrlImagen('fotos/yapo/123.avif')).toBe(`${CDN}/fotos/yapo/123.avif`);
    expect(resolverUrlImagen('/fotos/yapo/123.avif')).toBe(`${CDN}/fotos/yapo/123.avif`);
  });

  it('deja pasar las URL absolutas de los orígenes permitidos', async () => {
    const { resolverUrlImagen } = await importarCdn();
    expect(resolverUrlImagen(`${CDN}/fotos/yapo/123.avif`)).toBe(`${CDN}/fotos/yapo/123.avif`);
    expect(resolverUrlImagen(`${SUPABASE}/storage/v1/object/public/avisos/1.webp`)).toBe(
      `${SUPABASE}/storage/v1/object/public/avisos/1.webp`,
    );
  });

  it('descarta las URL absolutas de cualquier otro origen', async () => {
    const { resolverUrlImagen } = await importarCdn();
    expect(resolverUrlImagen('https://evil.example/pixel.gif?c=1')).toBeNull();
    expect(resolverUrlImagen('http://www.autocosmos.cl/thumb.webp')).toBeNull();
    // Un subdominio que empieza igual no es el mismo origen.
    expect(resolverUrlImagen(`${CDN}.evil.example/x.png`)).toBeNull();
    // Ni el mismo host por otro puerto.
    expect(resolverUrlImagen('https://img.carflip.cl:8443/x.png')).toBeNull();
  });

  it('devuelve null cuando no hay imagen', async () => {
    const { resolverUrlImagen } = await importarCdn();
    expect(resolverUrlImagen(null)).toBeNull();
    expect(resolverUrlImagen('')).toBeNull();
  });
});
