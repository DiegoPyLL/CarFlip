import { describe, expect, it } from 'vitest';

import { COOKIE_SESION, rutaInterna, tieneCookieSesion } from '@lib/auth/servidor';

/**
 * Las dos comprobaciones de `auth/servidor.ts` que un desconocido controla por
 * completo: a dónde se puede mandar a un usuario después de entrar, y qué basta
 * para que el sitio gaste una llamada de red validando una sesión inexistente.
 */

const conCookie = (cookie: string) => new Request('https://carflip.cl/', { headers: { Cookie: cookie } });

describe('rutaInterna', () => {
  it('acepta rutas del propio sitio y conserva query y fragmento', () => {
    expect(rutaInterna('/avisos')).toBe('/avisos');
    expect(rutaInterna('/avisos?marca=Toyota&pagina=2')).toBe('/avisos?marca=Toyota&pagina=2');
    expect(rutaInterna('/auto/p/12#contacto')).toBe('/auto/p/12#contacto');
  });

  it('rechaza la barra invertida, que el parser de URL convierte en un host externo', () => {
    // El caso del advisory: `/\evil.com` pasaba el filtro de `//` y el navegador
    // lo resolvía a https://evil.com tras un login legítimo.
    expect(rutaInterna('/\\evil.com')).toBe('/');
    expect(rutaInterna('/\\/evil.com')).toBe('/');
    expect(rutaInterna('/\\\\evil.com')).toBe('/');
    expect(rutaInterna('\\\\evil.com')).toBe('/');
  });

  it('rechaza los destinos externos por las vías conocidas', () => {
    expect(rutaInterna('//evil.com')).toBe('/');
    expect(rutaInterna('https://evil.com')).toBe('/');
    expect(rutaInterna('http://carflip.cl.evil.com')).toBe('/');
    expect(rutaInterna('javascript:alert(1)')).toBe('/');
    expect(rutaInterna('data:text/html,<script>alert(1)</script>')).toBe('/');
    expect(rutaInterna('/\t/evil.com')).toBe('/');
    expect(rutaInterna('/\n\\evil.com')).toBe('/');
  });

  it('rechaza lo que no es una ruta, y respeta el destino por defecto', () => {
    expect(rutaInterna(null)).toBe('/');
    expect(rutaInterna(undefined)).toBe('/');
    expect(rutaInterna('')).toBe('/');
    expect(rutaInterna('avisos')).toBe('/');
    expect(rutaInterna('/\\evil.com', '/cuenta')).toBe('/cuenta');
    expect(rutaInterna(null, '/avisos')).toBe('/avisos');
  });

  it('deja la barra invertida codificada como parte de la ruta, no como host', () => {
    // `%5C` no lo decodifica el parser en el path: el destino sigue siendo interno.
    expect(rutaInterna('/%5Cevil.com')).toBe('/%5Cevil.com');
  });
});

describe('tieneCookieSesion', () => {
  it('reconoce la cookie del proyecto, entera o partida en trozos', () => {
    expect(tieneCookieSesion(conCookie(`${COOKIE_SESION}=eyJhbGci`))).toBe(true);
    expect(tieneCookieSesion(conCookie(`${COOKIE_SESION}.0=eyJ; ${COOKIE_SESION}.1=hbGci`))).toBe(true);
    expect(tieneCookieSesion(conCookie(`tema=oscuro; ${COOKIE_SESION}=eyJhbGci`))).toBe(true);
  });

  it('no cuenta la cookie del proyecto sin valor', () => {
    expect(tieneCookieSesion(conCookie(`${COOKIE_SESION}=`))).toBe(false);
  });

  it('no se deja forzar por una cookie cualquiera que contenga "sb-"', () => {
    expect(tieneCookieSesion(conCookie('sb-x=1'))).toBe(false);
    expect(tieneCookieSesion(conCookie('sb-=1'))).toBe(false);
    expect(tieneCookieSesion(conCookie('no-sb-auth-token=1'))).toBe(false);
    expect(tieneCookieSesion(conCookie('sb-otro-proyecto-auth-token=abc'))).toBe(false);
  });

  it('no cuenta una request sin cookies', () => {
    expect(tieneCookieSesion(new Request('https://carflip.cl/'))).toBe(false);
    expect(tieneCookieSesion(conCookie(''))).toBe(false);
  });
});
