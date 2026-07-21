#!/usr/bin/env node
// Smoke test de integración: consulta la API real de Resend para confirmar
// el estado de verificación del dominio de envío. Requiere RESEND_API_KEY
// (ver .env en la raíz del repo). No es un test unitario: hace una llamada
// de red real y depende de credenciales. Requiere una API key "Full access";
// una key restringida a "Sending access" no puede leer /domains.

const DOMINIO = process.env.RESEND_DOMAIN || 'carflip.cl';
const API_KEY = process.env.RESEND_API_KEY;

async function obtenerJson(ruta) {
  const respuesta = await fetch(`https://api.resend.com${ruta}`, {
    headers: { Authorization: `Bearer ${API_KEY}` },
  });
  if (!respuesta.ok) {
    const cuerpo = await respuesta.text();
    throw new Error(`Resend respondió ${respuesta.status} en ${ruta}: ${cuerpo}`);
  }
  return respuesta.json();
}

async function main() {
  if (!API_KEY) {
    throw new Error('RESEND_API_KEY no está configurada.');
  }

  const { data: dominios } = await obtenerJson('/domains');
  const dominio = dominios.find((d) => d.name === DOMINIO);
  if (!dominio) {
    throw new Error(`El dominio "${DOMINIO}" no está registrado en esta cuenta de Resend.`);
  }

  const detalle = await obtenerJson(`/domains/${dominio.id}`);

  console.log(`Dominio: ${detalle.name}`);
  console.log(`Estado general: ${detalle.status}`);
  console.log('Registros:');
  for (const registro of detalle.records ?? []) {
    console.log(`  - ${registro.record} (${registro.type} ${registro.name}): ${registro.status}`);
  }

  process.exitCode = detalle.status === 'verified' ? 0 : 1;
}

main().catch((error) => {
  console.error(error.message);
  process.exitCode = 1;
});
