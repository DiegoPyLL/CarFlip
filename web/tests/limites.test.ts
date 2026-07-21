import { describe, expect, it } from 'vitest';

import {
  LIMITES,
  MENSAJE_ERROR,
  PALABRA_ELIMINAR,
  confirmacionValida,
  mensajeDeError,
  perfilCompleto,
  puedeCrearAviso,
  puedeRevelarContacto,
  puedeSubirFoto,
} from '../src/lib/publicaciones/limites';

describe('puedeCrearAviso', () => {
  it('permite publicar bajo ambos topes', () => {
    expect(puedeCrearAviso(0, 0)).toBeNull();
    expect(puedeCrearAviso(LIMITES.avisosActivos - 1, LIMITES.creacionesPor24h - 1)).toBeNull();
  });

  it('bloquea al alcanzar el tope de avisos activos', () => {
    expect(puedeCrearAviso(LIMITES.avisosActivos, 0)).toBe('tope_activos');
  });

  it('bloquea al alcanzar el tope de creaciones en 24 h', () => {
    expect(puedeCrearAviso(0, LIMITES.creacionesPor24h)).toBe('tope_diario');
  });

  it('prioriza el tope de activos cuando se superan los dos', () => {
    expect(puedeCrearAviso(LIMITES.avisosActivos, LIMITES.creacionesPor24h)).toBe('tope_activos');
  });
});

describe('puedeSubirFoto', () => {
  it('permite una foto válida bajo el tope', () => {
    expect(puedeSubirFoto(0, 500_000, 'image/webp')).toBeNull();
    expect(puedeSubirFoto(LIMITES.fotosPorAviso - 1, LIMITES.bytesPorFoto, 'image/jpeg')).toBeNull();
  });

  it('bloquea al llegar al máximo de fotos del aviso', () => {
    expect(puedeSubirFoto(LIMITES.fotosPorAviso, 1000, 'image/webp')).toBe('tope_fotos');
  });

  it('bloquea las que superan 2 MB', () => {
    expect(puedeSubirFoto(0, LIMITES.bytesPorFoto + 1, 'image/webp')).toBe('foto_pesada');
  });

  it('bloquea los formatos no admitidos', () => {
    expect(puedeSubirFoto(0, 1000, 'image/gif')).toBe('formato_foto');
    expect(puedeSubirFoto(0, 1000, 'application/pdf')).toBe('formato_foto');
  });
});

describe('puedeRevelarContacto', () => {
  it('permite bajo el tope diario y bloquea al alcanzarlo', () => {
    expect(puedeRevelarContacto(LIMITES.revelacionesPorDia - 1)).toBeNull();
    expect(puedeRevelarContacto(LIMITES.revelacionesPorDia)).toBe('tope_revelaciones');
  });
});

describe('perfilCompleto', () => {
  it('exige nombre y teléfono con contenido', () => {
    expect(perfilCompleto({ nombre: 'Ana', telefono: '+56 9 12345678' })).toBe(true);
    expect(perfilCompleto({ nombre: '  ', telefono: '+56 9 12345678' })).toBe(false);
    expect(perfilCompleto({ nombre: 'Ana', telefono: null })).toBe(false);
    expect(perfilCompleto(null)).toBe(false);
  });
});

describe('confirmacionValida', () => {
  it('acepta la palabra exacta, con espacios sobrantes', () => {
    expect(confirmacionValida(PALABRA_ELIMINAR)).toBe(true);
    expect(confirmacionValida(`  ${PALABRA_ELIMINAR} `)).toBe(true);
  });

  it('rechaza variantes, vacíos y ausencias', () => {
    expect(confirmacionValida('eliminar')).toBe(false);
    expect(confirmacionValida('Eliminar')).toBe(false);
    expect(confirmacionValida('ELIMINAR TODO')).toBe(false);
    expect(confirmacionValida('')).toBe(false);
    expect(confirmacionValida(null)).toBe(false);
  });
});

describe('mensajeDeError', () => {
  it('traduce los códigos del catálogo', () => {
    expect(mensajeDeError('tope_activos')).toBe(MENSAJE_ERROR.tope_activos);
  });

  it('no refleja texto ajeno al catálogo', () => {
    const inyectado = 'Tu cuenta fue bloqueada, llama al +56 9 00000000';
    expect(mensajeDeError(inyectado)).toBe(MENSAJE_ERROR.servidor);
    expect(mensajeDeError('<script>alert(1)</script>')).toBe(MENSAJE_ERROR.servidor);
  });

  it('devuelve null si no hay código', () => {
    expect(mensajeDeError(null)).toBeNull();
  });
});
