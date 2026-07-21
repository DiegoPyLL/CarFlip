/**
 * Lectura y validación del formulario de aviso, compartida por crear y editar.
 *
 * El navegador ya valida con `required`/`min`/`max`/`pattern`, pero eso es
 * comodidad, no seguridad: aquí se vuelve a validar todo, porque un POST puede
 * llegar sin pasar por el formulario.
 */

import { normalizar } from '@lib/sanitizar';

import { ANIO_MINIMO, COMBUSTIBLES, REGIONES, TRANSMISIONES, anioMaximo } from './opciones';

export interface CamposAviso {
  titulo: string;
  marca: string;
  modelo: string;
  version: string | null;
  anio: number;
  km: number;
  precio: number;
  combustible: string | null;
  transmision: string | null;
  ubicacion: string;
  descripcion: string | null;
}

const KM_MAXIMO = 2_000_000;
const PRECIO_MAXIMO = 999_000_000;

function entero(valor: FormDataEntryValue | null): number | null {
  const texto = String(valor ?? '').replace(/[.\s]/g, '');
  if (!/^\d+$/.test(texto)) return null;
  const numero = Number(texto);
  return Number.isSafeInteger(numero) ? numero : null;
}

function deLista<T extends string>(valor: FormDataEntryValue | null, lista: readonly T[]): T | null {
  const texto = String(valor ?? '').trim();
  return (lista as readonly string[]).includes(texto) ? (texto as T) : null;
}

/** Devuelve las columnas listas para escribir, o `null` si algo no valida. */
export function camposDelFormulario(datos: FormData): CamposAviso | null {
  // Honeypot: invisible para personas, un bot que autocompleta todo lo llena.
  if (String(datos.get('web') ?? '').length > 0) return null;

  const marca = normalizar(datos.get('marca'), { max: 100 });
  const modelo = normalizar(datos.get('modelo'), { max: 100 });
  const version = normalizar(datos.get('version'), { max: 100 });
  const comuna = normalizar(datos.get('comuna'), { max: 100 });
  const descripcion = normalizar(datos.get('descripcion'), { max: 2000, preservarSaltos: true });

  const anio = entero(datos.get('anio'));
  const km = entero(datos.get('km'));
  const precio = entero(datos.get('precio'));
  const region = deLista(datos.get('region'), REGIONES);
  const combustible = deLista(datos.get('combustible'), COMBUSTIBLES);
  const transmision = deLista(datos.get('transmision'), TRANSMISIONES);

  if (!marca || !modelo || !comuna || !region) return null;
  if (anio === null || anio < ANIO_MINIMO || anio > anioMaximo()) return null;
  if (km === null || km > KM_MAXIMO) return null;
  if (precio === null || precio <= 0 || precio > PRECIO_MAXIMO) return null;

  return {
    titulo: [marca, modelo, version, anio].filter(Boolean).join(' '),
    marca,
    modelo,
    version: version || null,
    anio,
    km,
    precio,
    combustible,
    transmision,
    ubicacion: `${comuna}, ${region}`,
    descripcion: descripcion || null,
  };
}
