import type { FiltrosAviso } from './tipos';

export function parsearFiltrosUrl(params: URLSearchParams): FiltrosAviso {
  const filtros: FiltrosAviso = {};
  const anioActual = new Date().getFullYear();

  const fuente = params.get('fuente');
  if (fuente === 'autocosmos' || fuente === 'mercadolibre') {
    filtros.fuente = fuente;
  }

  const marca = params.get('marca')?.trim().slice(0, 100);
  if (marca) filtros.marca = marca;

  const modelo = params.get('modelo')?.trim().slice(0, 100);
  if (modelo) filtros.modelo = modelo;

  const anio = parseInt(params.get('anio') ?? '');
  if (!isNaN(anio) && anio >= 1950 && anio <= anioActual + 1) {
    filtros.anio = anio;
  }

  const precioMin = parseFloat(params.get('precio_min') ?? '');
  if (!isNaN(precioMin) && precioMin > 0) filtros.precio_min = precioMin;

  const precioMax = parseFloat(params.get('precio_max') ?? '');
  if (!isNaN(precioMax) && precioMax > 0) filtros.precio_max = precioMax;

  const kmMax = parseFloat(params.get('km_max') ?? '');
  if (!isNaN(kmMax) && kmMax > 0) filtros.km_max = kmMax;

  const combustible = params.get('combustible')?.trim().slice(0, 50);
  if (combustible) filtros.combustible = combustible;

  const pagina = parseInt(params.get('pagina') ?? '1');
  filtros.pagina = !isNaN(pagina) && pagina >= 1 ? pagina : 1;

  return filtros;
}
