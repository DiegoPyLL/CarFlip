import { afterEach, describe, expect, it, vi } from 'vitest';

/**
 * `revelarContacto` es la única puerta entre el teléfono de un vendedor y quien
 * lee el aviso: decide si sale, lo registra y aplica el tope diario. Se prueba
 * con dobles porque lo que importa aquí son las decisiones, no PostgREST.
 */

const perfil = vi.hoisted(() => ({
  valor: { nombre: 'Ana', telefono: '+56 9 1234 5678' } as { nombre: string | null; telefono: string | null } | null,
}));

vi.mock('@lib/db/client', () => ({
  supabase: {
    from: () => {
      const consulta: Record<string, unknown> = {
        select: () => consulta,
        eq: () => consulta,
        maybeSingle: () => Promise.resolve({ data: perfil.valor ? { perfiles: perfil.valor } : null }),
      };
      return consulta;
    },
  },
  POR_PAGINA: 24,
}));

const { revelarContacto } = await import('@lib/publicaciones/consultas');
const { LIMITES } = await import('@lib/publicaciones/limites');

/**
 * Cliente de sesión con la cadena de PostgREST: los filtros devuelven el mismo
 * objeto y el `await` resuelve el siguiente conteo de la cola, en el orden en
 * que la función los pide (primero "¿ya lo reveló?", después "¿cuántas hoy?").
 */
function clienteSesion(conteos: number[], errorInsert: { message: string } | null = null) {
  const cola = [...conteos];
  const insert = vi.fn(() => Promise.resolve({ error: errorInsert }));
  const from = vi.fn(() => {
    const consulta: Record<string, unknown> = {
      select: () => consulta,
      eq: () => consulta,
      gte: () => consulta,
      insert,
      then: (resolver: (v: { count: number }) => unknown) =>
        Promise.resolve({ count: cola.shift() ?? 0 }).then(resolver),
    };
    return consulta;
  });
  return { cliente: { from } as never, from, insert };
}

const USUARIO = '11111111-1111-1111-1111-111111111111';

afterEach(() => {
  perfil.valor = { nombre: 'Ana', telefono: '+56 9 1234 5678' };
  vi.restoreAllMocks();
});

describe('revelarContacto', () => {
  it('entrega el contacto y registra la revelación la primera vez', async () => {
    const { cliente, insert } = clienteSesion([0, 3]);

    const resultado = await revelarContacto(cliente, 7, USUARIO);

    expect(resultado).toEqual({
      estado: 'ok',
      contacto: {
        nombre: 'Ana',
        telefono: '+56 9 1234 5678',
        tel: 'tel:+56912345678',
        whatsapp: 'https://wa.me/56912345678',
      },
    });
    expect(insert).toHaveBeenCalledWith({ aviso_id: 7, usuario_id: USUARIO });
  });

  it('no vuelve a registrar ni gasta cupo si ya lo había revelado', async () => {
    const { cliente, insert } = clienteSesion([1]);

    const resultado = await revelarContacto(cliente, 7, USUARIO);

    expect(resultado.estado).toBe('ok');
    expect(insert).not.toHaveBeenCalled();
  });

  it('no entrega el teléfono al alcanzar el tope diario', async () => {
    const { cliente, insert } = clienteSesion([0, LIMITES.revelacionesPorDia]);

    const resultado = await revelarContacto(cliente, 7, USUARIO);

    expect(resultado).toEqual({ estado: 'tope' });
    expect(insert).not.toHaveBeenCalled();
  });

  it('no entrega el teléfono si la revelación no se pudo registrar', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    const { cliente } = clienteSesion([0, 0], { message: 'RLS' });

    expect(await revelarContacto(cliente, 7, USUARIO)).toEqual({ estado: 'error' });
  });

  it('no consulta cupo ni registra nada si el vendedor no tiene teléfono', async () => {
    perfil.valor = null;
    const { cliente, from, insert } = clienteSesion([0, 0]);

    expect(await revelarContacto(cliente, 7, USUARIO)).toEqual({ estado: 'sin_telefono' });
    expect(from).not.toHaveBeenCalled();
    expect(insert).not.toHaveBeenCalled();
  });
});
