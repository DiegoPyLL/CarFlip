import { describe, expect, it, vi } from 'vitest';

/**
 * Cambio de contraseña. El bloqueo de pegado y el `minlength` del formulario son
 * UX: quien apague JavaScript o arme el POST a mano los evita, así que lo que se
 * prueba aquí es que el servidor no dependa de ellos, y que la reautenticación
 * de Supabase no deje al usuario en un callejón sin salida.
 */

const ORIGIN = 'https://carflip.cl';
const CLAVE = 'contrasena-larga';
const NONCE = '12345678';

const USUARIO = {
  id: 'b3f1c2d4-0000-4000-8000-000000000001',
  email: 'ana@carflip.cl',
  emailConfirmado: true,
  emailPendiente: '',
  rol: 'usuario' as const,
};

type Fallo = { message: string; code?: string } | null;

function clienteFalso(fallo: Fallo = null, falloReauth: Fallo = null) {
  const updateUser = vi.fn(async () => ({ data: {}, error: fallo }));
  const reauthenticate = vi.fn(async () => ({ data: {}, error: falloReauth }));
  return { cliente: { auth: { updateUser, reauthenticate } } as any, updateUser, reauthenticate };
}

function crearRequest(campos: Record<string, string>): Request {
  const datos = new FormData();
  for (const [clave, valor] of Object.entries(campos)) datos.append(clave, valor);
  return new Request(`${ORIGIN}/api/cuenta/contrasena`, { method: 'POST', body: datos });
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

const enviar = async (
  campos: Record<string, string>,
  fallo: Fallo = null,
  usuario: unknown = USUARIO,
  falloReauth: Fallo = null,
) => {
  vi.resetModules();
  const { cliente, updateUser, reauthenticate } = clienteFalso(fallo, falloReauth);
  const { POST } = await import('../../src/pages/api/cuenta/contrasena');
  const respuesta = await POST(contexto(crearRequest(campos), cliente, usuario) as never);
  return { destino: ubicacionDe(respuesta as Response), updateUser, reauthenticate };
};

const par = (password: string, confirmacion = password) => ({
  password,
  password_confirmacion: confirmacion,
});

describe('/api/cuenta/contrasena', () => {
  it('guarda la contraseña nueva y no manda nonce si no hizo falta', async () => {
    const { destino, updateUser } = await enviar(par(CLAVE));
    expect(updateUser).toHaveBeenCalledWith({ password: CLAVE });
    expect(destino).toBe('/cuenta/seguridad?estado=contrasena_guardada');
  });

  it('revalida el largo mínimo aunque el formulario lo haya dejado pasar', async () => {
    for (const clave of ['', '1234567', 'siete12']) {
      const { destino, updateUser } = await enviar(par(clave));
      expect(destino).toBe('/cuenta/seguridad?error=clave_corta');
      expect(updateUser).not.toHaveBeenCalled();
    }
  });

  it('revalida la coincidencia aunque el bloqueo de pegado se haya sorteado', async () => {
    const { destino, updateUser } = await enviar(par(CLAVE, `${CLAVE}-otra`));
    expect(destino).toBe('/cuenta/seguridad?error=clave_distinta');
    expect(updateUser).not.toHaveBeenCalled();
  });

  it('no acepta espacios como confirmación de una clave vacía', async () => {
    const { destino, updateUser } = await enviar({ password: '        ', password_confirmacion: '        ' });
    // Ocho espacios pasan el largo, y así debe ser: recortarlos cambiaría en
    // silencio la clave que el usuario eligió. Lo que no puede es reventar.
    expect(updateUser).toHaveBeenCalledWith({ password: '        ' });
    expect(destino).toBe('/cuenta/seguridad?estado=contrasena_guardada');
  });

  it('pasa el nonce solo cuando tiene el largo de un código real', async () => {
    const conNonce = await enviar({ ...par(CLAVE), nonce: NONCE });
    expect(conNonce.updateUser).toHaveBeenCalledWith({ password: CLAVE, nonce: NONCE });

    for (const nonce of ['', '1234', 'abcdefgh', '123456789']) {
      const { updateUser } = await enviar({ ...par(CLAVE), nonce });
      expect(updateUser).toHaveBeenCalledWith({ password: CLAVE });
    }
  });

  it('pide el código a Supabase cuando exige reautenticar, no solo lo anuncia', async () => {
    // Sin esta llamada la página prometía un correo que nunca salía y el usuario
    // quedaba esperando un código inexistente.
    const { destino, reauthenticate } = await enviar(par(CLAVE), {
      message: 'Reauthentication required',
      code: 'reauthentication_needed',
    });
    expect(reauthenticate).toHaveBeenCalledOnce();
    expect(destino).toBe('/cuenta/seguridad?error=reautenticar');
  });

  it('avisa del fallo si además no se pudo mandar ese código', async () => {
    const { destino } = await enviar(
      par(CLAVE),
      { message: 'Reauthentication required', code: 'reauthentication_needed' },
      USUARIO,
      { message: 'over_email_send_rate_limit' },
    );
    expect(destino).toBe('/cuenta/seguridad?error=servidor');
  });

  it('distingue el nonce inválido del que falta, para poder reintentar', async () => {
    for (const code of ['reauthentication_not_valid', 'reauth_nonce_missing']) {
      const { destino } = await enviar({ ...par(CLAVE), nonce: NONCE }, { message: 'nope', code });
      expect(destino).toBe('/cuenta/seguridad?error=nonce_invalido');
    }
  });

  it('traduce los rechazos que el usuario puede corregir', async () => {
    const repetida = await enviar(par(CLAVE), { message: 'same', code: 'same_password' });
    expect(repetida.destino).toBe('/cuenta/seguridad?error=clave_repetida');

    const debil = await enviar(par(CLAVE), { message: 'weak', code: 'weak_password' });
    expect(debil.destino).toBe('/cuenta/seguridad?error=clave_debil');
  });

  it('lo que no puede corregir el usuario cae en el error genérico', async () => {
    const { destino } = await enviar(par(CLAVE), { message: 'boom', code: 'unexpected_failure' });
    expect(destino).toBe('/cuenta/seguridad?error=servidor');
  });

  it('sin sesión manda a entrar', async () => {
    const { destino, updateUser } = await enviar(par(CLAVE), null, null);
    expect(destino).toBe('/entrar?volver=/cuenta/seguridad');
    expect(updateUser).not.toHaveBeenCalled();
  });
});
