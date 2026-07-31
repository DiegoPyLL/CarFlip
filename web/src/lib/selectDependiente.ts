/**
 * Selects en cascada sin JavaScript de por medio en el servidor.
 *
 *   <select id="region">…</select>
 *   <select data-grupos-de="region">
 *     <optgroup label="Metropolitana">…</optgroup>
 *     <optgroup label="Valparaíso">…</optgroup>
 *   </select>
 *
 * El HTML trae todos los `<optgroup>`, así que el formulario funciona servido
 * tal cual: se elige la comuna —o el modelo— de la lista completa. Este script
 * solo deja a la vista el grupo que corresponde a lo elegido arriba, que es lo
 * que evita recorrer el país entero para encontrar Ñuñoa.
 *
 * Los grupos que sobran salen del DOM y viven en un Map: la lista no se duplica
 * en el bundle, se reusa la que ya vino en el HTML.
 *
 * Se monta solo al importarse. Lo importan `CamposUbicacion` y `CamposVehiculo`;
 * como es el mismo módulo, se ejecuta una vez aunque los dos estén en la página.
 */

function montar() {
  for (const dependiente of document.querySelectorAll<HTMLSelectElement>('select[data-grupos-de]')) {
    const padre = document.getElementById(dependiente.dataset.gruposDe!);
    if (!(padre instanceof HTMLSelectElement)) continue;

    const grupos = new Map(
      [...dependiente.querySelectorAll('optgroup')].map((g): [string, HTMLOptGroupElement] => [g.label, g]),
    );

    const sincronizar = () => {
      const elegido = grupos.get(padre.value);
      for (const grupo of grupos.values()) if (grupo !== elegido) grupo.remove();
      if (elegido && !elegido.isConnected) dependiente.append(elegido);

      // Al quitar el <option> seleccionado el navegador deja el select en -1:
      // volver al placeholder evita mandar un par incoherente al cambiar de
      // padre. Sin nada elegido arriba no hay qué ofrecer, así que se apaga.
      if (!dependiente.value) dependiente.selectedIndex = 0;
      dependiente.disabled = !elegido;

      // Quien dependa de este select —el datalist de versiones— necesita
      // enterarse de que su valor pudo cambiar, y `selectedIndex` no dispara
      // eventos por sí solo.
      dependiente.dispatchEvent(new Event('change', { bubbles: true }));
    };

    padre.addEventListener('change', sincronizar);
    sincronizar();

    // Al recargar o volver atrás el navegador repone el valor del padre sin
    // disparar `change`: sin esto la lista de abajo quedaría en la anterior.
    window.addEventListener('pageshow', sincronizar);
  }
}

montar();
