import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const ORIGIN = 'https://carflip.cl';

function crearRequest(campos: Record<string, string>): Request {
  const datos = new FormData();
  for (const [clave, valor] of Object.entries(campos)) datos.append(clave, valor);
  return new Request(`${ORIGIN}/contacto`, { method: 'POST', body: datos });
}

async function importarPOST() {
  vi.resetModules();
  const modulo = await import('../src/pages/api/contacto');
  return modulo.POST;
}

function ubicacionDe(respuesta: Response): string {
  return respuesta.headers.get('location') ?? '';
}

describe('POST /api/contacto', () => {
  beforeEach(() => {
    process.env.RESEND_API_KEY = 'test-key';
    process.env.CONTACT_EMAIL = 'contacto@carflip.cl';
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    delete process.env.RESEND_API_KEY;
    delete process.env.CONTACT_EMAIL;
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

  it('escapa HTML en los campos del formulario', async () => {
    vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({ id: 'abc' }), { status: 200 }));
    const POST = await importarPOST();
    const request = crearRequest({
      nombre: '<script>alert(1)</script>',
      email: 'ana@example.com',
      mensaje: 'hola',
    });

    await POST({ request, url: new URL(`${ORIGIN}/contacto`) } as any);

    const [, opciones] = vi.mocked(fetch).mock.calls[0];
    const cuerpo = JSON.parse(opciones?.body as string);
    expect(cuerpo.html).not.toContain('<script>');
    expect(cuerpo.html).toContain('&lt;script&gt;');
  });
});
