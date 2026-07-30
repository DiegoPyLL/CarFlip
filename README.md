<p align="center">
  <img src="carflip_logo.png" alt="CarFlip" width="100%">
</p>

<p align="center">
  <strong>Un comparador de precios de autos usados en Chile.</strong><br>
  <a href="https://carflip.cl">carflip.cl</a>
</p>

---

## El problema

Comprar un auto usado en Chile es a ciegas. Ves un Yaris 2018 a $8.900.000 y no tienes cómo saber si eso está bien, mal o es una estafa. Habría que revisar decenas de avisos parecidos, anotarlos y sacar cuentas — nadie lo hace.

CarFlip hace esa cuenta por ti.

## Qué hace

**Reúne los autos en venta.** Cualquier persona puede publicar el suyo, gratis, creando una cuenta. Las automotoras aportan su catálogo. Todo queda en un mismo listado, con los mismos campos y los mismos filtros.

**Calcula cuánto vale cada auto.** Para un aviso cualquiera, CarFlip toma todos los avisos comparables —misma marca, mismo modelo, año similar, kilometraje parecido— y saca el precio típico del grupo. Usa la mediana y no el promedio, porque un par de precios disparatados no la mueven. Si hay muy pocos comparables, no calcula nada: mejor no mostrar una referencia poco confiable.

**Marca las oportunidades.** Los avisos bastante por debajo de su mercado llegan a la página [/deals](https://carflip.cl/deals).

**Y las revisa antes de mostrarlas.** Un precio bajo no siempre es una ganga: puede ser un auto chocado, sin papeles o con el motor malo. Antes de publicar cada oportunidad, una IA lee la descripción del aviso y la clasifica en *oportunidad clara*, *buen precio*, *revisar* o *descartar*, con un puntaje y los riesgos que detectó.

## Cómo está armado

Dos piezas que casi no se hablan entre sí. Comparten la base de datos, y nada más.

```
   El sitio (Astro)                    El analizador (Python)
   Vercel · atiende a las              GitHub Actions · corre una
   visitas y recibe los                vez al día, calcula precios
   avisos que se publican              de mercado y oportunidades
            │                                     │
            └──────────────┬──────────────────────┘
                           ▼
              Supabase — PostgreSQL + fotos
```

El sitio se arma en el servidor y llega al navegador como HTML listo, sin JavaScript propio. De ahí vienen la velocidad de carga y el posicionamiento en buscadores, que son la prioridad del proyecto.

| Pieza | Tecnología |
| --- | --- |
| Sitio | Astro 7 (SSR) + Tailwind 4, desplegado en Vercel |
| Base de datos, cuentas y fotos | Supabase (PostgreSQL, Auth y Storage) |
| Analizador | Python 3.12, corriendo en GitHub Actions |
| Evaluación de oportunidades | Groq (Llama 3.3) |

### Dónde está cada cosa

```
web/                  El sitio: páginas, componentes y consultas
src/carflip/          El analizador: detección de deals y precios de mercado
alembic/              Historial de cambios de la base de datos
supabase/             Permisos del bucket de fotos
tests/                Tests del analizador (los del sitio están en web/tests/)
.github/workflows/    Tareas programadas
docker/               Imagen con que corren esas tareas
```

## Publicar un auto

Se crea una cuenta y el aviso aparece al instante, sin cola de revisión. Para que eso no se preste para abusos hay límites: correo confirmado y perfil completo antes de publicar, hasta 15 avisos por día, 10 fotos de 2 MB cada una, y patente obligatoria, validada contra los formatos legales chilenos. Un aviso que pasa 60 días sin tocarse se pausa solo. Cualquier visitante puede reportar un aviso, y el administrador lo baja desde el panel interno.

**El teléfono del vendedor nunca aparece en el HTML público.** Sin sesión iniciada se ve `+56 9 •••• ••••`; hay que entrar para verlo, cada visualización queda registrada y hay un tope diario. Así el número no termina recolectado por un bot.

**Los permisos viven en la base de datos, no en el código del sitio.** Aunque alguien evite la interfaz y hable directo con la base, no puede editar avisos ajenos, poner precios negativos ni saltarse los límites: las reglas están escritas abajo, donde no hay forma de rodearlas.

## Levantarlo

El `.env` va en la **raíz del repositorio**, no dentro de `web/`: el sitio y el analizador comparten el mismo archivo.

### El sitio

Es lo habitual y lo más simple: no necesitas Python ni una base de datos local, todo conecta a Supabase por internet. Requiere **Node 22.12+**.

```bash
git clone https://github.com/DiegoPyLL/CarFlip
cd CarFlip/web
npm install
npm run dev     # → http://localhost:4321
```

Variables que necesita:

| Variable | Para qué | Si falta |
| --- | --- | --- |
| `SUPABASE_URL` | Proyecto de Supabase | El sitio no parte |
| `SUPABASE_SERVICE_KEY` | Lecturas públicas del catálogo | El sitio no parte |
| `PUBLIC_SUPABASE_URL` | Cuentas y sesiones | El sitio funciona, sin login |
| `PUBLIC_SUPABASE_ANON_KEY` | Ídem | El sitio funciona, sin login |
| `RESEND_API_KEY` | Envío del formulario de contacto | `/contacto` da error |
| `CONTACT_EMAIL` | Dónde llegan esos mensajes | `/contacto` da error |
| `CDN_BASE_URL` | Dominio de las imágenes | Las fotos no cargan |

> El prefijo `PUBLIC_` es a propósito: esa clave está hecha para llegar al navegador, y quien limita lo que puede hacer es la base de datos. **`SUPABASE_SERVICE_KEY` nunca debe llevarlo** — esa sí es secreta y da acceso total.

Detalle del stack, estructura y despliegue en **[web/README.md](web/README.md)**.

### El analizador

Requiere **Python 3.12** y [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run alembic upgrade head   # poner la base al día
uv run carflip deals          # buscar y clasificar oportunidades
```

Además de `DATABASE_URL` (con `USE_SSL=true` para Supabase), necesita `GROQ_API_KEY` — se saca gratis en [console.groq.com](https://console.groq.com/keys). El resto de la configuración tiene valores por defecto razonables en [src/carflip/config.py](src/carflip/config.py).

| Comando | Qué hace |
| --- | --- |
| `carflip deals` | Busca oportunidades y las clasifica con IA |
| `carflip snapshot` | Guarda la foto del mercado de hoy |
| `carflip market <marca> <modelo> <año>` | Consulta precios de un modelo |

## Lo que corre solo

| Cuándo | Qué |
| --- | --- |
| Todos los días, 10:00 UTC | [`deals.yml`](.github/workflows/deals.yml) — recalcula las oportunidades |
| Martes, 19:00 UTC | [`auditoria.yml`](.github/workflows/auditoria.yml) — audita vulnerabilidades de las dependencias y abre un aviso de seguridad si encuentra algo |

Ambas se pueden lanzar a mano desde la pestaña **Actions → Run workflow**.

> GitHub desactiva las tareas programadas si el repositorio pasa 60 días sin commits. Se reactivan con un clic en esa misma pestaña.

## Documentación

| Archivo | Qué contiene |
| --- | --- |
| [web/README.md](web/README.md) | Stack, estructura y despliegue del sitio |
| [web/DESIGN.md](web/DESIGN.md) | Sistema visual: colores, tipografía y reglas por componente |
| [CHANGELOG.md](CHANGELOG.md) | Qué cambió en cada versión |
| [CLAUDE.md](CLAUDE.md) | Los principios con que se toman las decisiones técnicas aquí |
