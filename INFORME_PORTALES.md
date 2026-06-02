
# Informe de Portales de Vehículos Usados en Chile y Evaluación de Scraping para Carflip

## Objetivo
Identificar portales relevantes de venta de vehículos usados en Chile, excluyendo:

- Chileautos.cl
- Yapo.cl
- MercadoLibre
- Autocosmos.cl
- Autosusados.cl
- Kavak
- Económicos (El Mercurio)
- AutoRemates
- AMotor
- Autofact.cl

Además, evaluar si los Términos y Condiciones de cada portal permiten o restringen actividades de scraping, almacenamiento de anuncios y redirección hacia la publicación original.

## Resumen Ejecutivo
El análisis muestra que la mayoría de los portales no ofrecen APIs públicas para acceso a publicaciones de vehículos.

Existen tres escenarios predominantes:
1. Prohibición explícita del scraping y reutilización de contenido.
2. Ausencia de regulación específica en los Términos y Condiciones.
3. Protección implícita mediante derechos de autor y propiedad intelectual.

El modelo utilizado por Carflip consiste en:
- Recopilar anuncios.
- Almacenar información estructurada.
- Indexar publicaciones.
- Redirigir al usuario al portal original para concretar el contacto o compra.

Este modelo reduce parte del riesgo comercial respecto a republicar anuncios completos, pero no elimina posibles conflictos contractuales ni de propiedad intelectual.

## Portales Identificados

| Portal | Tipo |
| :--- | :--- |
| Ruta100 | Marketplace |
| Clicar | Marketplace |
| FullMotor | Marketplace |
| Bruno Fritsch Usados | Concesionario |
| Gildemeister Usados | Concesionario |
| Salfa Usados | Concesionario |
| Portillo Usados | Concesionario |
| Movicenter Usados | Marketplace |
| Automotriz Rosselot Usados | Concesionario |
| DercoCenter Usados | Concesionario |
| Usados Coseche | Concesionario |
| SKBergé Usados | Concesionario |
| Kovacs Usados | Concesionario |
| Williamson Balfour Usados | Concesionario |
| Nissan Marubeni Usados | Concesionario |
| Pompeyo Carrasco Usados | Concesionario |
| PortalAutos.cl | Clasificados |
| Macal | Remates |
| Karcal | Remates |
| Copart | Remates |

## Evaluación de Riesgo para Carflip

### Clicar
**Restricción encontrada:** Los términos indican que el contenido no puede ser copiado, distribuido, explotado comercialmente ni reutilizado sin autorización escrita.

| Actividad | Riesgo |
| :--- | :--- |
| Scraping | Alto |
| Almacenamiento | Alto |
| Publicación de fotos | Muy Alto |
| Publicación de textos | Muy Alto |
| Solo redirección | Bajo |

**Conclusión:** Carflip podría recibir objeciones si almacena o publica contenido de Clicar.

### Karcal
**Restricción encontrada:** Expresa que está prohibida la descarga o cualquier alteración de los contenidos publicados.

| Actividad | Riesgo |
| :--- | :--- |
| Scraping | Muy Alto |
| Almacenamiento | Muy Alto |
| Reutilización | Muy Alto |
| Redirección | Bajo |

**Conclusión:** Karcal es uno de los portales más restrictivos analizados.

### Macal
No fue posible encontrar una cláusula pública tan explícita como Karcal. Sin embargo, no existe API pública y los remates suelen proteger comercialmente sus bases de publicaciones.

| Actividad | Riesgo |
| :--- | :--- |
| Scraping | Alto |
| Almacenamiento | Alto |
| Redirección | Bajo |

### Bruno Fritsch, Gildemeister Usados, FullMotor
No se encontraron prohibiciones explícitas respecto al scraping en estos portales.

| Actividad | Riesgo |
| :--- | :--- |
| Scraping | Medio |
| Almacenamiento | Medio |
| Redirección | Bajo |

## Clasificación General de Riesgo

### Riesgo Muy Alto
- Karcal
- Clicar

### Riesgo Alto
- Macal
- Copart

### Riesgo Medio
- Ruta100, FullMotor, Bruno Fritsch, Gildemeister, Salfa, Rosselot, Portillo, Movicenter, DercoCenter, SKBergé, Kovacs, Williamson Balfour, Nissan Marubeni, Pompeyo Carrasco, PortalAutos.

## Impacto para Carflip

### Situación Actual
Carflip obtiene anuncios, almacena información, indexa publicaciones y redirige al anuncio original.

### Riesgos Principales
1. **Contractuales:** Si un sitio prohíbe el scraping, el operador puede solicitar eliminación, bloqueo de IPs o cese de indexación.
2. **Propiedad Intelectual:** Riesgo al almacenar fotografías, descripciones completas, logos y marcas.
3. **Base de Datos:** Argumentos sobre protección de la compilación de anuncios.

## Recomendaciones para Carflip

### Nivel Mínimo (Seguro)
Guardar únicamente: URL original, ID de publicación, marca, modelo, año, precio.
Evitar: Fotografías, descripciones completas, información de contacto.

### Nivel Recomendado
Mostrar: Título resumido (generado internamente), precio, marca, modelo, ubicación.
Acción: Dirigir inmediatamente al portal original.

### Nivel Óptimo
Negociar acuerdos directos con Macal, Karcal, Movicenter, Rosselot, Salfa, Bruno Fritsch y DercoCenter para obtener autorización expresa de indexación.



## Evaluación Matemática del Riesgo
Para cuantificar el riesgo técnico-legal de realizar scraping en cada portal, se propone el siguiente Índice de Riesgo de Scraping ($R_s$):

$$\Large R_s = (D_w \times P_i) + (C_r \times A_e)$$

### Definición de variables:
- **$R_s$**: Índice de Riesgo de Scraping (Escala de 0 a 1).
- **$D_w$**: **Densidad de Datos Web**: Cantidad de campos extraídos (fotos, descripciones, contactos).
- **$P_i$**: **Ponderación de Propiedad Intelectual**: Valor asignado al tipo de contenido (las fotos tienen un peso superior a metadatos básicos).
- **$C_r$**: **Coeficiente de Restricción Contractual**: Severidad de los T&C del portal (0.1 para ausencia de regulación, 1.0 para prohibición explícita).
- **$A_e$**: **Actividad de Extracción**: Frecuencia del scraping o volumen de peticiones realizadas por IP.

### Interpretación Estratégica:
1. **Minimización de $D_w$**: Al reducir los campos extraídos (ej. eliminar fotos), el valor de $R_s$ disminuye drásticamente, situándose en el "Nivel Mínimo" de seguridad.
2. **Mitigación de $C_r$**: Obtener acuerdos formales reduce el $C_r$ a valores cercanos a 0, permitiendo indexar más contenido de forma lícita.

## Conclusión
El modelo basado en agregación y redirección presenta menos riesgo que republicar anuncios completos. Sin embargo, para portales como Karcal y Clicar existe una incompatibilidad evidente con sus términos. La estrategia jurídicamente más sólida consiste en indexar metadatos mínimos, evitar almacenar activos digitales (fotos/descripciones), respetar `robots.txt` y buscar acuerdos formales.

