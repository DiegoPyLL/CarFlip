// Re-exporta todo desde los módulos de BD para que los imports existentes
// usando '@lib/db' sigan funcionando sin cambios.

export { obtenerAvisos, obtenerAviso, obtenerFiltrosDisponibles } from './avisos';
export { obtenerDeals, obtenerFiltrosDeals } from './deals';
export {
  obtenerDatosMercado,
  obtenerDatosMarca,
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
export { obtenerMetricasOperacion, obtenerMetricasVehiculos } from './metricas';
