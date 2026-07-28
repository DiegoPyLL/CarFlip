import { describe, expect, it, vi } from 'vitest';

const ORIGIN = 'https://carflip.cl';

const USUARIO = { id: 'b3f1c2d4-0000-4000-8000-000000000001', email: 'ana@carflip.cl' };

const VALIDOS = {
  nombre: 'Ana Pérez',
  telefono: '9 1234 5678',
  region: 'Tarapacá',
  comuna: 'Iquique',
};

type Resultado = { data: { id: string } | null; error: { message: string } | null };

/**
 * Doble del cliente ligado a la sesión. Devuelve también la cadena para poder
 * afirmar sobre lo que se mandó a escribir, no solo sobre el redirect.
 */
function clienteFalso(resultado: Resultado) {
  const cadena = {
    update: vi.fn(() => cadena),
    eq: vi.fn(() => cadena),
    select: vi.fn(() => cadena),
    maybeSingle: vi.fn(async () => resultado),
  };
  const from = vi.fn(() => cadena);
  return { cliente: { from } as any, from, cadena };
}

function crearRequest(campos: Record<string, string>): Request {
  const datos = new FormData();
  for (const [clave, valor] of Object.entries(campos)) datos.append(clave, valor);
  return new Request(`${ORIGIN}/api/cuenta/perfil`, { method: 'POST', body: datos });
}

function contexto(request: Request, supabase: unknown, usuario: unknown = USUARIO) {
  return {
    request,
    locals: { usuario, supabase },
    redirect: (destino: string, estado = 302) =>
      new Response(null, { status: estado, headers: { location: destino } }),
  } as any;
}

async function importarPOST() {
  vi.resetModules();
  const modulo = await import('../../src/pages/api/cuenta/perfil');
  return modulo.POST;
}

function ubicacionDe(respuesta: Response): string {
  return respuesta.headers.get('location') ?? '';
}

/** Envía `campos` y devuelve a dónde redirigió, con el UPDATE resuelto como `resultado`. */
async function enviar(campos: Record<string, string>, resultado: Resultado = { data: { id: USUARIO.id }, error: null }) {
  const { cliente, from, cadena } = clienteFalso(resultado);
  const POST = await importarPOST();
  const respuesta = await POST(contexto(crearRequest(campos), cliente));
  return { destino: ubicacionDe(respuesta), from, cadena };
}

describe('POST /api/cuenta/perfil', () => {
  it('guarda y confirma cuando el UPDATE alcanza la fila', async () => {
    const { destino, from, cadena } = await enviar(VALIDOS);

    expect(destino).toBe('/cuenta?guardado=1');
    expect(from).toHaveBeenCalledWith('perfiles');
    expect(cadena.eq).toHaveBeenCalledWith('id', USUARIO.id);
  });

  it('normaliza el teléfono antes de escribirlo', async () => {
    const { cadena } = await enviar({ ...VALIDOS, telefono: '+56 9 1234-5678' });

    expect(cadena.update).toHaveBeenCalledWith(expect.objectContaining({ telefono: '+56 9 12345678' }));
  });

  // Issue #43: las cuentas anteriores al trigger de la 0010 no tenían fila en
  // `perfiles`, así que el UPDATE no tocaba ninguna y PostgREST lo devolvía sin
  // error. El endpoint confirmaba "Datos guardados." sobre un guardado que nunca
  // ocurrió, y la página seguía pidiendo completar nombre y teléfono.
  it('no confirma el guardado si el UPDATE no tocó ninguna fila', async () => {
    const { destino } = await enviar(VALIDOS, { data: null, error: null });

    expect(destino).toBe('/cuenta?error=servidor');
  });

  it('avisa del fallo cuando Supabase devuelve error', async () => {
    const { destino } = await enviar(VALIDOS, { data: null, error: { message: 'permission denied' } });

    expect(destino).toBe('/cuenta?error=servidor');
  });

  it.each([
    ['nombre vacío', { nombre: '   ' }],
    ['nombre con dígitos', { nombre: 'Ana 2' }],
    ['teléfono que no es móvil chileno', { telefono: '221234567' }],
    ['teléfono con letras', { telefono: 'novecientos' }],
    ['región inexistente', { region: 'Selecciona...' }],
    ['comuna de otra región', { comuna: 'Arica' }],
    ['comuna heredada del prototipo', { region: 'toString', comuna: 'toString' }],
  ])('rechaza %s sin tocar la base', async (_caso, invalido) => {
    const { destino, from } = await enviar({ ...VALIDOS, ...invalido });

    expect(destino).toBe('/cuenta?error=datos');
    expect(from).not.toHaveBeenCalled();
  });

  it('manda a entrar si no hay sesión', async () => {
    const { cliente, from } = clienteFalso({ data: null, error: null });
    const POST = await importarPOST();

    const respuesta = await POST(contexto(crearRequest(VALIDOS), cliente, null));

    expect(ubicacionDe(respuesta)).toBe('/entrar?volver=/cuenta');
    expect(from).not.toHaveBeenCalled();
  });
});
