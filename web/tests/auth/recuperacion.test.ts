import { describe, expect, it, vi } from 'vitest';

/**
 * Los dos endpoints de recuperación de contraseña, empujados con lo que manda un
 * desconocido: el primero no puede delatar qué direcciones tienen cuenta, y el
 * segundo no puede gastar una llamada de red por cada código con forma inválida.
 */

const ORIGIN = 'https://carflip.cl';
const EMAIL = 'ana@carflip.cl';
const CODIGO = '12345678';

type Fallo = { message: string } | null;

function clienteFalso(fallo: Fallo = null) {
  const resetPasswordForEmail = vi.fn(async () => ({ data: {}, error: fallo }));
  const verifyOtp = vi.fn(async () => ({ data: {}, error: fallo }));
  return { cliente: { auth: { resetPasswordForEmail, verifyOtp } } as any, resetPasswordForEmail, verifyOtp };
}

/** Doble de `AstroCookies`: solo hace falta saber si se tocó la cookie, no cómo. */
function cookiesFalsas() {
  return { set: vi.fn(), delete: vi.fn(), get: vi.fn() } as any;
}

function crearRequest(campos: Record<string, string>, ruta: string): Request {
  const datos = new FormData();
  for (const [clave, valor] of Object.entries(campos)) datos.append(clave, valor);
  return new Request(`${ORIGIN}${ruta}`, { method: 'POST', body: datos });
}

function contexto(request: Request, supabase: unknown, cookies: unknown) {
  return {
    request,
    cookies,
    locals: { supabase },
    redirect: (destino: string, estado = 302) =>
      new Response(null, { status: estado, headers: { location: destino } }),
  } as any;
}

const ubicacionDe = (respuesta: Response) => respuesta.headers.get('location') ?? '';

async function importar(modulo: string) {
  vi.resetModules();
  return (await import(modulo)).POST;
}

describe('/api/auth/recuperar', () => {
  const enviar = async (campos: Record<string, string>, fallo: Fallo = null) => {
    const { cliente, resetPasswordForEmail } = clienteFalso(fallo);
    const POST = await importar('../../src/pages/api/auth/recuperar');
    const respuesta = await POST(
      contexto(crearRequest(campos, '/api/auth/recuperar'), cliente, cookiesFalsas()),
    );
    return { destino: ubicacionDe(respuesta), resetPasswordForEmail };
  };

  it('responde igual con cuenta existente que con el error de Supabase', async () => {
    // Es lo único que impide usar este formulario como detector de usuarios: si
    // el fallo se propagara, bastaría probar direcciones y mirar el redirect.
    const existe = await enviar({ email: EMAIL });
    const noExiste = await enviar({ email: 'nadie@carflip.cl' }, { message: 'User not found' });

    expect(existe.destino).toBe('/recuperar-contrasena?enviado=1');
    expect(noExiste.destino).toBe(existe.destino);
  });

  it('normaliza el correo antes de mandarlo', async () => {
    const { resetPasswordForEmail } = await enviar({ email: '  ANA@CarFlip.CL  ' });
    expect(resetPasswordForEmail).toHaveBeenCalledWith(EMAIL);
  });

  it('rechaza los correos malformados sin llamar a Supabase', async () => {
    for (const email of ['', '   ', 'ana', 'ana@', '@carflip.cl', 'ana carflip.cl', 'ana@carflip']) {
      const { destino, resetPasswordForEmail } = await enviar({ email });
      expect(destino).toBe('/recuperar-contrasena?error=email');
      expect(resetPasswordForEmail).not.toHaveBeenCalled();
    }
  });

  it('distingue el reenvío del primer envío', async () => {
    const { destino } = await enviar({ email: EMAIL, reenviar: '1' });
    expect(destino).toBe('/recuperar-contrasena?enviado=1&reenviado=1');
  });

  it('sin las variables de Supabase avisa en vez de romperse', async () => {
    const POST = await importar('../../src/pages/api/auth/recuperar');
    const respuesta = await POST(
      contexto(crearRequest({ email: EMAIL }, '/api/auth/recuperar'), null, cookiesFalsas()),
    );
    expect(ubicacionDe(respuesta)).toBe('/recuperar-contrasena?error=config');
  });
});

describe('/api/auth/recuperar/confirmar', () => {
  const enviar = async (campos: Record<string, string>, fallo: Fallo = null) => {
    const { cliente, verifyOtp } = clienteFalso(fallo);
    const cookies = cookiesFalsas();
    const POST = await importar('../../src/pages/api/auth/recuperar/confirmar');
    const respuesta = await POST(
      contexto(crearRequest(campos, '/api/auth/recuperar/confirmar'), cliente, cookies),
    );
    return { destino: ubicacionDe(respuesta), verifyOtp, cookies };
  };

  it('canjea el código por una sesión y manda a fijar la contraseña', async () => {
    const { destino, verifyOtp, cookies } = await enviar({ email: EMAIL, codigo: CODIGO });

    expect(verifyOtp).toHaveBeenCalledWith({ email: EMAIL, token: CODIGO, type: 'recovery' });
    expect(destino).toBe('/cuenta/seguridad?recuperacion=1');
    expect(cookies.delete).toHaveBeenCalled();
  });

  it('descarta los códigos con forma inválida sin gastar una llamada de red', async () => {
    for (const codigo of ['', '1234567', '123456789', 'abcdefgh', '1234abcd', '   ']) {
      const { destino, verifyOtp } = await enviar({ email: EMAIL, codigo });
      expect(destino).toBe('/recuperar-contrasena?enviado=1&error=codigo');
      expect(verifyOtp).not.toHaveBeenCalled();
    }
  });

  it('acepta el código con separadores, que es como se pega desde el correo', async () => {
    const { verifyOtp } = await enviar({ email: EMAIL, codigo: '1234 5678' });
    expect(verifyOtp).toHaveBeenCalledWith({ email: EMAIL, token: CODIGO, type: 'recovery' });
  });

  it('da el mismo mensaje al código errado, al expirado y a la cuenta inexistente', async () => {
    const errado = await enviar({ email: EMAIL, codigo: CODIGO }, { message: 'Token has expired' });
    const inexistente = await enviar({ email: 'nadie@carflip.cl', codigo: CODIGO }, { message: 'User not found' });

    expect(errado.destino).toBe('/recuperar-contrasena?enviado=1&error=codigo');
    expect(inexistente.destino).toBe(errado.destino);
  });

  it('no deja una sesión a medias: si el canje falla, la cookie del correo sigue en pie', async () => {
    const { cookies } = await enviar({ email: EMAIL, codigo: CODIGO }, { message: 'Token has expired' });
    expect(cookies.delete).not.toHaveBeenCalled();
  });
});
