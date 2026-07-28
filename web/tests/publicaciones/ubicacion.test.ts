import { experimental_AstroContainer as AstroContainer } from 'astro/container';
import { describe, expect, it } from 'vitest';

import CamposUbicacion from '../../src/components/cuenta/CamposUbicacion.astro';
import { camposDelFormulario } from '../../src/lib/publicaciones/formulario';
import { COMUNAS_POR_REGION, REGIONES, comunaEnRegion } from '../../src/lib/publicaciones/opciones';

describe('comunaEnRegion', () => {
  it('acepta el par que corresponde, en cualquier región', () => {
    expect(comunaEnRegion('Metropolitana', 'Ñuñoa')).toBe(true);
    expect(comunaEnRegion('Arica y Parinacota', 'Putre')).toBe(true);
    expect(comunaEnRegion('Magallanes', 'Torres del Paine')).toBe(true);
  });

  it('rechaza la comuna de otra región, que es el caso del issue', () => {
    expect(comunaEnRegion('Metropolitana', 'Arica')).toBe(false);
    expect(comunaEnRegion('Tarapacá', 'Ñuñoa')).toBe(false);
  });

  it('distingue los nombres que son región y comuna a la vez', () => {
    // O'Higgins es la región del Libertador y también una comuna de Aysén.
    expect(comunaEnRegion('Aysén', "O'Higgins")).toBe(true);
    expect(comunaEnRegion("O'Higgins", "O'Higgins")).toBe(false);

    // Los Lagos es región, y además una comuna de Los Ríos.
    expect(comunaEnRegion('Los Ríos', 'Los Lagos')).toBe(true);
    expect(comunaEnRegion('Los Lagos', 'Los Lagos')).toBe(false);

    // Aysén es comuna de su propia región; Antofagasta también.
    expect(comunaEnRegion('Aysén', 'Aysén')).toBe(true);
    expect(comunaEnRegion('Antofagasta', 'Antofagasta')).toBe(true);
  });

  it('rechaza la región inventada y la comuna inventada', () => {
    expect(comunaEnRegion('Región 25', 'Ñuñoa')).toBe(false);
    expect(comunaEnRegion('Metropolitana', 'Springfield')).toBe(false);
    expect(comunaEnRegion('', '')).toBe(false);
    expect(comunaEnRegion('Metropolitana', '')).toBe(false);
    expect(comunaEnRegion('', 'Ñuñoa')).toBe(false);
  });

  it('no acepta el nombre con basura alrededor ni con otra caja', () => {
    expect(comunaEnRegion(' Metropolitana', 'Ñuñoa')).toBe(false);
    expect(comunaEnRegion('Metropolitana', 'Ñuñoa ')).toBe(false);
    expect(comunaEnRegion('METROPOLITANA', 'Ñuñoa')).toBe(false);
    expect(comunaEnRegion('Metropolitana', 'nunoa')).toBe(false);
    expect(comunaEnRegion('Metropolitana', '<script>alert(1)</script>')).toBe(false);
  });

  it('no confunde las claves del prototipo con regiones', () => {
    for (const clave of ['__proto__', 'constructor', 'toString', 'hasOwnProperty', 'valueOf']) {
      expect(comunaEnRegion(clave, 'Ñuñoa')).toBe(false);
      expect(comunaEnRegion(clave, clave)).toBe(false);
    }
  });
});

describe('COMUNAS_POR_REGION', () => {
  it('tiene las 16 regiones y las 346 comunas', () => {
    expect(REGIONES).toHaveLength(16);
    expect(Object.keys(COMUNAS_POR_REGION)).toEqual([...REGIONES]);
    expect(Object.values(COMUNAS_POR_REGION).flat()).toHaveLength(346);
  });

  it('no repite un nombre de comuna entre regiones', () => {
    // De esto depende que el par región/comuna sea deducible sin ambigüedad.
    const todas = Object.values(COMUNAS_POR_REGION).flat();
    expect(new Set(todas).size).toBe(todas.length);
  });
});

/** Un aviso mínimo válido; cada test cambia solo lo que quiere probar. */
function avisoValido(cambios: Record<string, string> = {}): FormData {
  const datos = new FormData();
  const base: Record<string, string> = {
    marca: 'Toyota',
    modelo: 'Corolla',
    anio: '2020',
    km: '45000',
    precio: '12000000',
    patente: 'GSBB20',
    region: 'Metropolitana',
    comuna: 'Ñuñoa',
    ...cambios,
  };
  for (const [clave, valor] of Object.entries(base)) datos.set(clave, valor);
  return datos;
}

describe('camposDelFormulario, ubicación', () => {
  it('arma "Comuna, Región" cuando el par calza', () => {
    expect(camposDelFormulario(avisoValido())?.ubicacion).toBe('Ñuñoa, Metropolitana');
  });

  it('descarta el aviso cuya comuna no es de esa región', () => {
    expect(camposDelFormulario(avisoValido({ comuna: 'Arica' }))).toBeNull();
    expect(camposDelFormulario(avisoValido({ region: 'Aysén' }))).toBeNull();
  });

  it('descarta la región o la comuna que no existen', () => {
    expect(camposDelFormulario(avisoValido({ region: 'Metropolitana de Santiago' }))).toBeNull();
    expect(camposDelFormulario(avisoValido({ comuna: 'Ñuñoa, Metropolitana' }))).toBeNull();
    expect(camposDelFormulario(avisoValido({ region: '', comuna: '' }))).toBeNull();
    expect(camposDelFormulario(avisoValido({ region: '__proto__' }))).toBeNull();
  });
});

describe('CamposUbicacion, el HTML servido', () => {
  const render = async (props?: { region?: string; comuna?: string }) =>
    (await AstroContainer.create()).renderToString(CamposUbicacion, { props: props ?? {} });

  it('sirve las 346 comunas en sus 16 grupos: es la versión sin JavaScript', async () => {
    const html = await render();
    expect(html.match(/<optgroup/g)).toHaveLength(REGIONES.length);
    // Las 346 más los dos placeholder "Selecciona…" y las 16 regiones.
    const comunas = Object.values(COMUNAS_POR_REGION).flat().length;
    expect(html.match(/<option/g)).toHaveLength(comunas + REGIONES.length + 2);
  });

  it('deja preseleccionado el par guardado', async () => {
    const html = await render({ region: 'Los Ríos', comuna: 'Panguipulli' });
    expect(html).toContain('<option value="Los Ríos" selected>');
    expect(html).toContain('<option value="Panguipulli" selected>');
    expect(html.match(/selected/g)).toHaveLength(2);
  });

  it('enlaza comuna con región para el filtrado en el cliente', async () => {
    const html = await render();
    expect(html).toContain('data-comunas-de="region"');
    expect(html).toContain('id="region"');
    expect(html).not.toContain('selected');
  });
});
