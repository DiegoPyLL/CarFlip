// Re-exporta todo desde los módulos de BD para que los imports existentes
// usando '@lib/db' sigan funcionando sin cambios.

export { obtenerAvisos, obtenerAviso, obtenerFiltrosDisponibles } from './avisos';
export { obtenerDeals } from './deals';
export { obtenerDatosMercado, obtenerDatosMarca } from './mercado';
export type { EstadisticaMarca, EstadisticaModelo, DatosMercado } from './mercado';
export { obtenerEstadisticas } from './estadisticas';
