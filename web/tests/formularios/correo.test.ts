import { describe, expect, it, vi } from 'vitest';

/**
 * Cambio de correo. Lo que se prueba aquí no es que funcione el camino feliz,
 * sino que las dos direcciones en juego salgan siempre de la sesión: si alguna
 * se leyera del formulario, quien tuviera la sesión abierta podría desviar el
 * cambio a un buzón propio entre que la página se dibuja y el POST se envía.
 */

const ORIGIN = 'https://carflip.cl';
const ACTUAL = 'ana@carflip.cl';
const NUEVO = 'ana.nueva@carflip.cl';
const CODIGO_A = '11111111';
const CODIGO_B = '22222222';

const USUARIO = {
  id: 'b3f1c2d4-0000-4000-8000-000000000001',
  email: ACTUAL,
  emailConfirmado: true,
  emailPendiente: '',
  rol: 'usuario' as const,
};

type Fallo = { message: string; code?: string } | null;

function clienteFalso(fallos: Fallo[] = [null]) {
  const restantes = [...fallos];
  const siguiente = () => ({ data: {}, error: restantes.length > 1 ? restantes.shift()! : restantes[0] });
  const updateUser = vi.fn(async () => siguiente());
  const verifyOtp = vi.fn(async () => siguiente());
  return { cliente: { auth: { updateUser, verifyOtp } } as any, updateUser, verifyOtp };
}

function crearRequest(campos: Record<string, string>, ruta: string): Request {
  const datos = new FormData();
  for (const [clave, valor] of Object.entries(campos)) datos.append(clave, valor);
  return new Request(`${ORIGIN}${ruta}`, { method: 'POST', body: datos });
}

function contexto(request: Request, supabase: unknown, usuario: unknown) {
  return {
    request,
    locals: { usuario, supabase },
    redirect: (destino: string, estado = 302) =>
      new Response(null, { status: estado, headers: { location: destino } }),
  } as any;
}

const ubicacionDe = (respuesta: Response) => respuesta.headers.get('location') ?? '';

/** El primer argumento de cada llamada al doble, ya tipado: los dobles de `vi.fn` no lo conservan. */
const argumentosDe = (doble: { mock: { calls: unknown[][] } }) =>
  doble.mock.calls.map(([primero]) => primero as { email: string; token: string; type: string });

async function importar(modulo: string) {
  vi.resetModules();
  return (await import(modulo)).POST;
}

describe('/api/cuenta/correo', () => {
  const enviar = async (
    campos: Record<string, string>,
    usuario: unknown = USUARIO,
    fallo: Fallo = null,
  ) => {
    const { cliente, updateUser } = clienteFalso([fallo]);
    const POST = await importar('../../src/pages/api/cuenta/correo');
    const respuesta = await POST(
      contexto(crearRequest(campos, '/api/cuenta/correo'), cliente, usuario),
    );
    return { destino: ubicacionDe(respuesta), updateUser };
  };

  it('inicia el cambio y deja a Supabase mandar los dos códigos', async () => {
    const { destino, updateUser } = await enviar({ email: NUEVO });
    expect(updateUser).toHaveBeenCalledWith({ email: NUEVO });
    expect(destino).toBe('/cuenta/seguridad?estado=correo_enviado');
  });

  it('rechaza el correo que ya es el actual, aunque venga con otra caja', async () => {
    for (const email of [ACTUAL, '  ANA@CARFLIP.CL  ']) {
      const { destino, updateUser } = await enviar({ email });
      expect(destino).toBe('/cuenta/seguridad?error=correo_igual');
      expect(updateUser).not.toHaveBeenCalled();
    }
  });

  it('rechaza los correos malformados sin llamar a Supabase', async () => {
    for (const email of ['', 'ana', 'ana@', '@carflip.cl', 'ana carflip.cl']) {
      const { destino, updateUser } = await enviar({ email });
      expect(destino).toBe('/cuenta/seguridad?error=correo_invalido');
      expect(updateUser).not.toHaveBeenCalled();
    }
  });

  it('en el reenvío ignora el correo del formulario y usa el de la sesión', async () => {
    // El caso que importa: un POST fabricado a mano que intenta desviar el cambio
    // a otra dirección aprovechando el botón de reenviar.
    const conPendiente = { ...USUARIO, emailPendiente: NUEVO };
    const { updateUser } = await enviar({ reenviar: '1', email: 'atacante@evil.com' }, conPendiente);
    expect(updateUser).toHaveBeenCalledWith({ email: NUEVO });
  });

  it('no reenvía nada si no hay un cambio en curso', async () => {
    const { destino, updateUser } = await enviar({ reenviar: '1', email: NUEVO });
    expect(destino).toBe('/cuenta/seguridad?error=correo_sin_cambio');
    expect(updateUser).not.toHaveBeenCalled();
  });

  it('traduce el correo ya tomado en vez de responder un error genérico', async () => {
    const { destino } = await enviar({ email: NUEVO }, USUARIO, {
      message: 'Email already exists',
      code: 'email_exists',
    });
    expect(destino).toBe('/cuenta/seguridad?error=correo_en_uso');
  });

  it('sin sesión manda a entrar, no a un 500', async () => {
    const { destino } = await enviar({ email: NUEVO }, null);
    expect(destino).toBe('/entrar?volver=/cuenta/seguridad');
  });
});

describe('/api/cuenta/correo/confirmar', () => {
  const conPendiente = { ...USUARIO, emailPendiente: NUEVO };

  const enviar = async (
    campos: Record<string, string>,
    usuario: unknown = conPendiente,
    fallos: Fallo[] = [null],
  ) => {
    const { cliente, verifyOtp } = clienteFalso(fallos);
    const POST = await importar('../../src/pages/api/cuenta/correo/confirmar');
    const respuesta = await POST(
      contexto(crearRequest(campos, '/api/cuenta/correo/confirmar'), cliente, usuario),
    );
    return { destino: ubicacionDe(respuesta), verifyOtp };
  };

  it('canjea los dos códigos, el de la dirección vieja primero', async () => {
    const { destino, verifyOtp } = await enviar({ codigo_actual: CODIGO_A, codigo_nuevo: CODIGO_B });

    expect(verifyOtp).toHaveBeenNthCalledWith(1, { email: ACTUAL, token: CODIGO_A, type: 'email_change' });
    expect(verifyOtp).toHaveBeenNthCalledWith(2, { email: NUEVO, token: CODIGO_B, type: 'email_change' });
    expect(destino).toBe('/cuenta/seguridad?estado=correo_guardado');
  });

  it('ignora las direcciones que vengan en el POST y usa las de la sesión', async () => {
    // El ataque directo: inyectar `email` o `email_actual` para que el canje
    // apunte a un buzón ajeno. Los campos sobran y no deben leerse.
    const { verifyOtp } = await enviar({
      codigo_actual: CODIGO_A,
      codigo_nuevo: CODIGO_B,
      email: 'atacante@evil.com',
      email_actual: 'atacante@evil.com',
      email_nuevo: 'atacante@evil.com',
    });

    const direcciones = argumentosDe(verifyOtp).map(({ email }) => email);
    expect(direcciones).toEqual([ACTUAL, NUEVO]);
  });

  it('no canjea ninguno si falta uno de los dos, para no quemar el par', async () => {
    // Cada token es de un solo uso: gastar el primero y descubrir después que el
    // segundo venía vacío dejaba el cambio a medias y sin forma de terminarlo.
    const incompletos: Record<string, string>[] = [
      { codigo_actual: CODIGO_A, codigo_nuevo: '' },
      { codigo_actual: '', codigo_nuevo: CODIGO_B },
      { codigo_actual: CODIGO_A, codigo_nuevo: '1234' },
      { codigo_actual: 'abcdefgh', codigo_nuevo: CODIGO_B },
      {},
    ];

    for (const campos of incompletos) {
      const { destino, verifyOtp } = await enviar(campos);
      expect(destino).toBe('/cuenta/seguridad?error=correo_codigo');
      expect(verifyOtp).not.toHaveBeenCalled();
    }
  });

  it('corta en el primer canje fallido y no intenta el segundo', async () => {
    const { destino, verifyOtp } = await enviar(
      { codigo_actual: CODIGO_A, codigo_nuevo: CODIGO_B },
      conPendiente,
      [{ message: 'Token has expired' }],
    );
    expect(verifyOtp).toHaveBeenCalledTimes(1);
    expect(destino).toBe('/cuenta/seguridad?error=correo_codigo');
  });

  it('sin cambio en curso no canjea nada, por más códigos que traiga', async () => {
    const { destino, verifyOtp } = await enviar(
      { codigo_actual: CODIGO_A, codigo_nuevo: CODIGO_B },
      USUARIO,
    );
    expect(destino).toBe('/cuenta/seguridad?error=correo_sin_cambio');
    expect(verifyOtp).not.toHaveBeenCalled();
  });
});
