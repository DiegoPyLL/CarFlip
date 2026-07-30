// Re-exporta todo desde los módulos de BD para que los imports existentes
// usando '@lib/db' sigan funcionando sin cambios.

export { obtenerAvisos, obtenerFiltrosDisponibles } from './avisos';
export { obtenerDeals, obtenerFiltrosDeals } from './deals';
export {
  obtenerDatosMercado,
  obtenerDatosMarca,
  obtenerMarcas,
  obtenerHistoriaMercado,
  consultarMercado,
  posicionMercado,
} from './mercado';
export type {
  EstadisticaMarca,
  EstadisticaModelo,
  DatosMercado,
  BucketHistograma,
  PrecioAnio,
  PuntoDia,
  PuntoHistoria,
  ConsultaMercado,
} from './mercado';
export { obtenerEstadisticas } from './estadisticas';
export { obtenerMetricasCatalogo } from './metricas';
