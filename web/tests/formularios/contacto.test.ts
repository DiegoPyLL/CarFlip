import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const ORIGIN = 'https://carflip.cl';

// El rate limit vive en una función de la base (migración 0019): acá se dobla el
// cliente de servicio para comprobar que el endpoint la consulta y la respeta.
const rpc = vi.hoisted(() => vi.fn());
vi.mock('@lib/db/client', () => ({ supabase: { rpc }, POR_PAGINA: 24 }));

function crearRequest(campos: Record<string, string>): Request {
  const datos = new FormData();
  for (const [clave, valor] of Object.entries(campos)) datos.append(clave, valor);
  return new Request(`${ORIGIN}/contacto`, { method: 'POST', body: datos });
}

async function importarPOST() {
  vi.resetModules();
  const modulo = await import('../../src/pages/api/contacto');
  return modulo.POST;
}

function ubicacionDe(respuesta: Response): string {
  return respuesta.headers.get('location') ?? '';
}

describe('POST /api/contacto', () => {
  beforeEach(() => {
    process.env.RESEND_API_KEY = 'test-key';
    process.env.CONTACT_EMAIL = 'contacto@carflip.cl';
    process.env.CONTACT_RATE_SALT = 'salt-de-prueba';
    rpc.mockReset();
    rpc.mockResolvedValue({ data: false, error: null });
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    delete process.env.RESEND_API_KEY;
    delete process.env.CONTACT_EMAIL;
    delete process.env.CONTACT_RATE_SALT;
  });

  it('descarta en silencio los envíos con honeypot lleno, sin llamar a Resend', async () => {
    const POST = await importarPOST();
    const request = crearRequest({
      nombre: 'Bot',
      email: 'bot@example.com',
      mensaje: 'spam',
      web: 'http://spam.example',
    });

    const respuesta = await POST({ request, url: new URL(`${ORIGIN}/contacto`) } as any);

    expect(respuesta.status).toBe(303);
    expect(ubicacionDe(respuesta)).toContain('enviado=1');
    expect(fetch).not.toHaveBeenCalled();
  });

  it('rechaza el envío si falta el nombre, el email o el mensaje', async () => {
    const POST = await importarPOST();
    const request = crearRequest({ nombre: '', email: 'a@a.com', mensaje: 'hola' });

    const respuesta = await POST({ request, url: new URL(`${ORIGIN}/contacto`) } as any);

    expect(respuesta.status).toBe(303);
    expect(ubicacionDe(respuesta)).toContain('error=1');
    expect(fetch).not.toHaveBeenCalled();
  });

  it('rechaza el envío si el email tiene formato inválido', async () => {
    const POST = await importarPOST();
    const request = crearRequest({ nombre: 'Ana', email: 'no-es-un-email', mensaje: 'hola' });

    const respuesta = await POST({ request, url: new URL(`${ORIGIN}/contacto`) } as any);

    expect(respuesta.status).toBe(303);
    expect(ubicacionDe(respuesta)).toContain('error=1');
    expect(fetch).not.toHaveBeenCalled();
  });

  it('responde error si RESEND_API_KEY no está configurada', async () => {
    delete process.env.RESEND_API_KEY;
    const POST = await importarPOST();
    const request = crearRequest({ nombre: 'Ana', email: 'ana@example.com', mensaje: 'hola' });

    const respuesta = await POST({ request, url: new URL(`${ORIGIN}/contacto`) } as any);

    expect(respuesta.status).toBe(303);
    expect(ubicacionDe(respuesta)).toContain('error=1');
    expect(fetch).not.toHaveBeenCalled();
  });

  it('responde error si CONTACT_EMAIL no está configurada, en vez de caer a una dirección del fuente', async () => {
    delete process.env.CONTACT_EMAIL;
    const POST = await importarPOST();
    const request = crearRequest({ nombre: 'Ana', email: 'ana@example.com', mensaje: 'hola' });

    const respuesta = await POST({ request, url: new URL(`${ORIGIN}/contacto`) } as any);

    expect(respuesta.status).toBe(303);
    expect(ubicacionDe(respuesta)).toContain('error=1');
    expect(fetch).not.toHaveBeenCalled();
  });

  it('falla cerrado si no hay salt para el hash de IP', async () => {
    // Sin salt secreto el hash de la IP es reversible por fuerza bruta, así que
    // el endpoint no envía en vez de guardar una IP efectivamente en claro.
    delete process.env.CONTACT_RATE_SALT;
    delete process.env.SUPABASE_SERVICE_KEY;
    const POST = await importarPOST();
    const request = crearRequest({ nombre: 'Ana', email: 'ana@example.com', mensaje: 'hola' });

    const respuesta = await POST({ request, url: new URL(`${ORIGIN}/contacto`) } as any);

    expect(respuesta.status).toBe(303);
    expect(ubicacionDe(respuesta)).toContain('error=1');
    expect(fetch).not.toHaveBeenCalled();
  });

  it('responde error si la API de Resend falla', async () => {
    vi.mocked(fetch).mockResolvedValue(new Response('mal remitente', { status: 422 }));
    const POST = await importarPOST();
    const request = crearRequest({ nombre: 'Ana', email: 'ana@example.com', mensaje: 'hola' });

    const respuesta = await POST({ request, url: new URL(`${ORIGIN}/contacto`) } as any);

    expect(respuesta.status).toBe(303);
    expect(ubicacionDe(respuesta)).toContain('error=1');
  });

  it('envía el correo a través de Resend y redirige a enviado', async () => {
    vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({ id: 'abc' }), { status: 200 }));
    const POST = await importarPOST();
    const request = crearRequest({ nombre: 'Ana', email: 'ana@example.com', mensaje: 'Hola,\nquiero info.' });

    const respuesta = await POST({ request, url: new URL(`${ORIGIN}/contacto`) } as any);

    expect(respuesta.status).toBe(303);
    expect(ubicacionDe(respuesta)).toContain('enviado=1');

    expect(fetch).toHaveBeenCalledTimes(1);
    const [endpoint, opciones] = vi.mocked(fetch).mock.calls[0];
    expect(endpoint).toBe('https://api.resend.com/emails');
    expect(opciones?.headers).toMatchObject({
      Authorization: 'Bearer test-key',
      'Content-Type': 'application/json',
    });

    const cuerpo = JSON.parse(opciones?.body as string);
    expect(cuerpo.to).toBe('contacto@carflip.cl');
    expect(cuerpo.reply_to).toBe('ana@example.com');
    expect(cuerpo.subject).toContain('Ana');
    expect(cuerpo.html).toContain('Hola,<br>quiero info.');
  });

  describe('rate limit por IP', () => {
    const enviar = async (POST: any) =>
      POST({
        request: crearRequest({ nombre: 'Ana', email: 'ana@example.com', mensaje: 'hola' }),
        url: new URL(`${ORIGIN}/contacto`),
        clientAddress: '203.0.113.7',
      });

    it('consulta la función de la base con la IP hasheada, nunca en claro', async () => {
      vi.mocked(fetch).mockResolvedValue(new Response('{}', { status: 200 }));
      const POST = await importarPOST();

      await enviar(POST);

      expect(rpc).toHaveBeenCalledTimes(1);
      const [nombre, args] = rpc.mock.calls[0];
      expect(nombre).toBe('registrar_solicitud_contacto');
      expect(args.p_ip_hash).toMatch(/^[0-9a-f]{64}$/);
      expect(args.p_ip_hash).not.toContain('203.0.113.7');
      expect(args.p_tope).toBe(5);
    });

    it('no llama a Resend cuando la IP superó el tope', async () => {
      rpc.mockResolvedValue({ data: true, error: null });
      const POST = await importarPOST();

      const respuesta = await enviar(POST);

      expect(respuesta.status).toBe(303);
      expect(ubicacionDe(respuesta)).toContain('error=1');
      expect(fetch).not.toHaveBeenCalled();
    });

    it('falla abierto si la base no responde: el contacto no depende de esta capa', async () => {
      rpc.mockRejectedValue(new Error('sin conexión'));
      vi.mocked(fetch).mockResolvedValue(new Response('{}', { status: 200 }));
      const POST = await importarPOST();

      const respuesta = await enviar(POST);

      expect(ubicacionDe(respuesta)).toContain('enviado=1');
      expect(fetch).toHaveBeenCalledTimes(1);
    });
  });

  it('escapa HTML en los campos del formulario', async () => {
    vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({ id: 'abc' }), { status: 200 }));
    const POST = await importarPOST();
    // El payload va en el mensaje: un nombre con `<` lo rechaza NOMBRE_RE antes
    // de llegar al escape, así que ahí no probaría nada.
    const request = crearRequest({
      nombre: 'Ana',
      email: 'ana@example.com',
      mensaje: '<script>alert(1)</script>',
    });

    await POST({ request, url: new URL(`${ORIGIN}/contacto`) } as any);

    const [, opciones] = vi.mocked(fetch).mock.calls[0];
    const cuerpo = JSON.parse(opciones?.body as string);
    expect(cuerpo.html).not.toContain('<script>');
    expect(cuerpo.html).toContain('&lt;script&gt;');
  });
});
