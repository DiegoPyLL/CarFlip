import { esFuente } from './db/fuentes';
import { REGIONES, TRACCIONES, TRANSMISIONES } from './publicaciones/opciones';
import type { CategoriaDeal, FiltrosAviso, FiltrosDeal } from './tipos';

/** Whitelist por coincidencia exacta: lo que no está en la lista no llega a la query. */
function deLista(valor: string | null, lista: readonly string[]): string | undefined {
  const texto = valor?.trim();
  return texto && lista.includes(texto) ? texto : undefined;
}

export function parsearFiltrosUrl(params: URLSearchParams): FiltrosAviso {
  const filtros: FiltrosAviso = {};
  const anioActual = new Date().getFullYear();

  // La lista válida sale de `TABLA_POR_FUENTE`: una fuente nueva se acepta sola
  // y cualquier otro valor se descarta en vez de llegar a la consulta.
  const fuente = params.get('fuente');
  if (esFuente(fuente)) filtros.fuente = fuente;

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
  if (!isNaN(kmMax) && kmMax >= 0) filtros.km_max = kmMax;

  const combustible = params.get('combustible')?.trim().slice(0, 50);
  if (combustible) filtros.combustible = combustible;

  // Región, transmisión y tracción son listas cerradas: se validan contra las
  // mismas constantes que llena el formulario de particulares, así que la web
  // nunca manda a la consulta un valor que la BD no pueda tener.
  const region = deLista(params.get('region'), REGIONES);
  if (region) filtros.region = region;

  const transmision = deLista(params.get('transmision'), TRANSMISIONES);
  if (transmision) filtros.transmision = transmision;

  const traccion = deLista(params.get('traccion'), TRACCIONES);
  if (traccion) filtros.traccion = traccion;

  const orden = params.get('orden');
  if (orden === 'reciente' || orden === 'precio_asc' || orden === 'precio_desc' || orden === 'km_asc') {
    filtros.orden = orden;
  }

  const pagina = parseInt(params.get('pagina') ?? '1');
  filtros.pagina = !isNaN(pagina) && pagina >= 1 ? pagina : 1;

  return filtros;
}

const CATEGORIAS_DEAL: readonly CategoriaDeal[] = ['oportunidad_clara', 'buen_precio', 'revisar'];

/**
 * Filtros de /deals: los mismos campos base que el listado, más categoría y
 * puntaje mínimo. `descartar` no es opción — esos deals no se muestran nunca,
 * así que aceptarla como filtro solo produciría una página vacía.
 */
export function parsearFiltrosDeals(params: URLSearchParams): FiltrosDeal {
  const filtros: FiltrosDeal = parsearFiltrosUrl(params);
  // El ranking de deals lo fija el algoritmo; un ?orden= en la URL se ignora.
  delete (filtros as FiltrosAviso).orden;

  const categoria = params.get('categoria')?.trim();
  if (categoria && (CATEGORIAS_DEAL as readonly string[]).includes(categoria)) {
    filtros.categoria = categoria as CategoriaDeal;
  }

  const puntajeMin = parseInt(params.get('puntaje_min') ?? '');
  if (!isNaN(puntajeMin) && puntajeMin > 0 && puntajeMin <= 100) {
    filtros.puntaje_min = puntajeMin;
  }

  return filtros;
}
