import { aEntero } from './campos';
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

  const marca = params.get('marca')?.trim().slice(0, 100);
  if (marca) filtros.marca = marca;

  const modelo = params.get('modelo')?.trim().slice(0, 100);
  if (modelo) filtros.modelo = modelo;

  // `aEntero` y no `parseFloat`: este último lee "1.500.000" como 1,5 —los
  // puntos de miles chilenos son su separador decimal—, así que una URL
  // compartida con el precio formateado filtraba por un peso y medio.
  const anio = aEntero(params.get('anio'));
  if (anio !== null && anio >= 1950 && anio <= anioActual + 1) {
    filtros.anio = anio;
  }

  const precioMin = aEntero(params.get('precio_min'));
  if (precioMin !== null && precioMin > 0) filtros.precio_min = precioMin;

  const precioMax = aEntero(params.get('precio_max'));
  if (precioMax !== null && precioMax > 0) filtros.precio_max = precioMax;

  const kmMax = aEntero(params.get('km_max'));
  if (kmMax !== null) filtros.km_max = kmMax;

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

  const pagina = aEntero(params.get('pagina'));
  filtros.pagina = pagina !== null && pagina >= 1 ? pagina : 1;

  return filtros;
}

/**
 * URL canónica de un listado (`/avisos`, `/deals`).
 *
 * Ningún filtro genera página indexable: son once parámetros, y `precio_min`,
 * `precio_max` y `km_max` aceptan cualquier entero, así que su combinatoria no
 * tiene tope. Todos canonicalizan al listado limpio, y con ellos cualquier
 * parámetro ajeno —`utm_*` y demás tracking— por el mismo camino.
 *
 * La paginación es la única excepción: sin filtros de por medio, cada página es
 * un tramo distinto del catálogo y se referencia a sí misma. Se exige que el
 * tramo exista, porque `?pagina=9999` renderiza un listado vacío que no tiene
 * nada que aportar al índice.
 */
export function canonicaListado(url: URL, pagina: number, totalPaginas: number): string {
  const soloPagina = [...url.searchParams.keys()].every((clave) => clave === 'pagina');
  const tramoReal = pagina > 1 && pagina <= totalPaginas;
  return soloPagina && tramoReal ? `${url.pathname}?pagina=${pagina}` : url.pathname;
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

  const puntajeMin = aEntero(params.get('puntaje_min'));
  if (puntajeMin !== null && puntajeMin > 0 && puntajeMin <= 100) {
    filtros.puntaje_min = puntajeMin;
  }

  return filtros;
}
