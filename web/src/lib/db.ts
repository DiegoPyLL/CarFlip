// Shim de compatibilidad — re-exporta todo desde los módulos en db/
// para que los imports existentes (@lib/db) sigan funcionando sin cambios.
export * from './db/avisos';
export * from './db/deals';
export * from './db/mercado';
export * from './db/estadisticas';
