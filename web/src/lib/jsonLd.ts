/**
 * Serializa un objeto para incrustarlo en un `<script type="application/ld+json">`.
 *
 * `JSON.stringify` no escapa `<`, `>` ni `&`, así que un `</script>` dentro de un
 * campo (título o descripción de un aviso) cerraría el script y permitiría
 * inyectar HTML/JS. Se escapan como secuencias unicode: siguen siendo JSON
 * válido —y schema.org las interpreta igual— pero el parser HTML ya no ve la
 * etiqueta de cierre. No usar escape de entidades HTML: rompería el JSON.
 */
export function scriptJsonLd(obj: unknown): string {
  return JSON.stringify(obj)
    .replace(/</g, '\\u003c')
    .replace(/>/g, '\\u003e')
    .replace(/&/g, '\\u0026');
}
