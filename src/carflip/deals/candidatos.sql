-- Candidatos a deal: outliers de precio respecto a su grupo comparable + bajadas de precio.
--
-- Parámetros vinculados (SQLAlchemy text()):
--   :umbral_pct       — % bajo la mediana del grupo para ser outlier (ej. 15)
--   :min_comparables  — mínimo de avisos por grupo marca/modelo/año (ej. 5)
--   :max_candidatos   — LIMIT de la corrida (ej. 200)
--
-- Decisiones de diseño:
--   * Grupo comparable = lower(trim(marca)), lower(trim(modelo)) + banda de año ±1:
--     amplía los comparables en mercados con pocos avisos por año exacto.
--   * Mediana (percentile_cont 0.5), no promedio: robusta ante los mismos
--     outliers que se busca detectar.
--   * km como guard, no como variable: si km > 1.5 × mediana_km del grupo,
--     el precio bajo lo explica el kilometraje y no es outlier.
--   * delta_pct como vía alternativa de entrada: un aviso que bajó fuerte de
--     precio es candidato aunque no sea outlier absoluto (umbral_pct / 3).
--   * disponible IS NOT FALSE: los scrapers que no llenan el campo (NULL)
--     no quedan excluidos.

WITH avisos AS (
    SELECT 'autocosmos' AS fuente, id_externo, url, titulo, marca, modelo, anio, km,
           precio, moneda, ubicacion, descripcion, url_imagen, delta_pct, disponible
    FROM autocosmos_listings
    UNION ALL
    SELECT 'yapo', id_externo, url, titulo, marca, modelo, anio, km,
           precio, moneda, ubicacion, descripcion, url_imagen, delta_pct, disponible
    FROM yapo_listings
    UNION ALL
    SELECT 'mercadolibre', id_externo, url, titulo, marca, modelo, anio, km,
           precio, moneda, ubicacion, descripcion, url_imagen, delta_pct, disponible
    FROM mercadolibre_listings
),
validos AS (
    SELECT a.*,
           lower(trim(a.marca))  AS marca_n,
           lower(trim(a.modelo)) AS modelo_n
    FROM avisos a
    WHERE a.disponible IS NOT FALSE
      AND a.precio IS NOT NULL AND a.precio > 0
      AND a.marca IS NOT NULL AND a.modelo IS NOT NULL AND a.anio IS NOT NULL
),
grupos AS (
    -- Estadísticas por grupo comparable: cada (marca, modelo, año) usa
    -- también los avisos de año ±1 como comparables.
    SELECT g.marca_n,
           g.modelo_n,
           g.anio,
           percentile_cont(0.5)  WITHIN GROUP (ORDER BY c.precio) AS precio_mediana,
           percentile_cont(0.25) WITHIN GROUP (ORDER BY c.precio) AS precio_p25,
           percentile_cont(0.5)  WITHIN GROUP (ORDER BY c.km)     AS km_mediana,
           count(*) AS comparables
    FROM (SELECT DISTINCT marca_n, modelo_n, anio FROM validos) g
    JOIN validos c
      ON c.marca_n = g.marca_n
     AND c.modelo_n = g.modelo_n
     AND c.anio BETWEEN g.anio - 1 AND g.anio + 1
    GROUP BY g.marca_n, g.modelo_n, g.anio
    HAVING count(*) >= :min_comparables
)
SELECT v.fuente,
       v.id_externo,
       v.url,
       v.titulo,
       v.marca,
       v.modelo,
       v.anio,
       v.km,
       v.precio,
       v.moneda,
       v.ubicacion,
       v.descripcion,
       v.url_imagen,
       v.delta_pct,
       round(g.precio_mediana::numeric, 0) AS precio_mercado,
       g.comparables,
       round(((v.precio - g.precio_mediana) / g.precio_mediana * 100)::numeric, 1) AS pct_vs_mercado
FROM validos v
JOIN grupos g
  ON v.marca_n = g.marca_n
 AND v.modelo_n = g.modelo_n
 AND v.anio = g.anio
WHERE
    -- Outlier estadístico: bien por debajo de la mediana del grupo...
    ( v.precio <= g.precio_mediana * (1 - :umbral_pct / 100.0)
      -- ...sin que el kilometraje lo explique.
      AND (v.km IS NULL OR g.km_mediana IS NULL OR v.km <= g.km_mediana * 1.5) )
    -- O bajada de precio significativa registrada por el uploader.
    OR v.delta_pct <= -(:umbral_pct / 3.0)
ORDER BY pct_vs_mercado ASC NULLS LAST
LIMIT :max_candidatos;
