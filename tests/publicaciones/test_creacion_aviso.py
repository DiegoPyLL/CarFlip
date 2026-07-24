"""Creación de un aviso de particular, contra Supabase real.

Publicar es la única escritura del sitio abierta a cualquiera con una cuenta, y
el aviso sale a la calle en el acto: no hay cola de revisión. Entre el navegador
y la tabla no queda nada más que las políticas RLS y los GRANT de las
migraciones 0010 y 0014, así que estos tests entran por donde entra el navegador
—anon key más el JWT del usuario— y comprueban tres cosas:

1. Que un usuario puede crear su aviso y que aparece donde debe.
2. Que no puede tocar el de otro, ni publicar a nombre de otro.
3. Qué hace la base cuando le llega basura: bytes nulos, controles, HTML,
   inyecciones, unicode raro, tipos equivocados y números fuera de rango.

El tercer bloque deja por escrito algo incómodo pero cierto: la base casi no
valida. Acepta precios negativos, kilometrajes negativos y cualquier `estado` que
quepa en 20 caracteres, y deja que un token válido se fije `vistas` a mano. Todo
eso lo detiene hoy `camposDelFormulario` en la web, y solo ahí.

Ejecutar con:

    pytest -m integration -v tests/publicaciones/ --supabase
"""

import pytest

from .conftest import ETIQUETA, PREFER, PREFIJO_EXTERNO, reintentar

pytestmark = pytest.mark.integration

TABLA = "/particulares_listings"


def codigo(respuesta) -> str:
    """SQLSTATE del error: afirma *por qué* falló, no solo que falló."""
    try:
        cuerpo = respuesta.json()
    except ValueError:
        return ""
    return str(cuerpo.get("code", "")) if isinstance(cuerpo, dict) else ""


async def crear(cliente, cuerpo):
    return await cliente.post(TABLA, json=cuerpo, headers=PREFER)


async def leer(servicio, id_externo):
    """Relee con la service key: importa lo que quedó en la fila, no lo que respondió la API."""
    respuesta = await servicio.get(TABLA, params={"id_externo": f"eq.{id_externo}", "select": "*"})
    return respuesta.json()


# ── El camino feliz ──────────────────────────────────────────────────────────


async def test_un_usuario_crea_su_aviso_y_nace_publicado(api, servicio, payload, usuario):
    """Sin `estado` explícito manda el server default, que es lo que hace el endpoint."""
    cuerpo = payload()
    del cuerpo["estado"]

    respuesta = await crear(api, cuerpo)

    assert respuesta.status_code == 201, respuesta.text[:300]
    guardado = (await leer(servicio, cuerpo["id_externo"]))[0]
    assert guardado["usuario_id"] == usuario.id
    assert guardado["estado"] == "publicado"
    assert guardado["moneda"] == "CLP"
    assert guardado["vistas"] == 0
    assert guardado["publicado_en"] is not None
    assert guardado["titulo"] == cuerpo["titulo"]


async def test_el_aviso_publicado_lo_ve_un_anonimo(api, anonimo, payload):
    """El contrato de la página pública: sin sesión se ven los publicados."""
    cuerpo = payload(estado="publicado")
    await crear(api, cuerpo)

    respuesta = await anonimo.get(TABLA, params={"id_externo": f"eq.{cuerpo['id_externo']}"})

    assert respuesta.status_code == 200, respuesta.text[:200]
    assert len(respuesta.json()) == 1


async def test_pausarlo_lo_saca_de_la_vista_anonima_pero_su_dueno_lo_sigue_viendo(
    api, anonimo, payload
):
    cuerpo = payload(estado="publicado")
    await crear(api, cuerpo)
    filtro = {"id_externo": f"eq.{cuerpo['id_externo']}"}

    pausa = await api.patch(TABLA, params=filtro, json={"estado": "pausado"}, headers=PREFER)

    assert pausa.status_code == 200, pausa.text[:200]
    assert (await anonimo.get(TABLA, params=filtro)).json() == []
    assert len((await api.get(TABLA, params=filtro)).json()) == 1


async def test_el_perfil_nace_vacio_con_la_cuenta(servicio, usuario_efimero):
    """El trigger crea el perfil sin nombre ni teléfono.

    Es justo lo que hace que `perfilCompleto` bloquee la publicación hasta que el
    usuario complete sus datos: si el trigger dejara de correr, publicar
    reventaría contra la foreign key en vez de mostrar el aviso de perfil.
    """
    perfil = await servicio.get("/perfiles", params={"id": f"eq.{usuario_efimero.id}", "select": "*"})

    fila = perfil.json()[0]
    assert fila["nombre"] is None
    assert fila["telefono"] is None


# ── Autorización: lo único que protege la creación ───────────────────────────


async def test_nadie_publica_a_nombre_de_otro(api, payload, otro_usuario):
    """`listings_insert_propio` compara el `usuario_id` contra `auth.uid()`."""
    respuesta = await crear(api, payload(usuario_id=otro_usuario.id))

    assert respuesta.status_code in (401, 403), respuesta.text[:200]
    assert codigo(respuesta) == "42501"


async def test_un_aviso_sin_dueno_no_entra(api, payload):
    cuerpo = payload()
    del cuerpo["usuario_id"]

    respuesta = await crear(api, cuerpo)

    # Lo puede cortar el NOT NULL o la política, según qué evalúe Postgres
    # primero; ambos son el resultado correcto.
    assert respuesta.status_code >= 400
    assert codigo(respuesta) in ("23502", "42501")


async def test_nadie_edita_el_aviso_de_otro(api, api_otro, servicio, payload):
    cuerpo = payload()
    await crear(api, cuerpo)
    filtro = {"id_externo": f"eq.{cuerpo['id_externo']}"}

    intento = await api_otro.patch(TABLA, params=filtro, json={"precio": 1}, headers=PREFER)

    assert intento.json() == [], "la política dejó editar un aviso ajeno"
    assert float((await leer(servicio, cuerpo["id_externo"]))[0]["precio"]) == 9500000


async def test_nadie_borra_el_aviso_de_otro(api, api_otro, servicio, payload):
    cuerpo = payload()
    await crear(api, cuerpo)

    intento = await api_otro.delete(
        TABLA, params={"id_externo": f"eq.{cuerpo['id_externo']}"}, headers=PREFER
    )

    assert intento.json() == [], "la política dejó borrar un aviso ajeno"
    assert len(await leer(servicio, cuerpo["id_externo"])) == 1


async def test_nadie_se_apropia_de_un_aviso_cambiandole_el_dueno(api, payload, otro_usuario):
    """El `WITH CHECK` del UPDATE: se puede editar lo propio, no regalarlo ni robarlo."""
    cuerpo = payload()
    await crear(api, cuerpo)

    intento = await api.patch(
        TABLA,
        params={"id_externo": f"eq.{cuerpo['id_externo']}"},
        json={"usuario_id": otro_usuario.id},
        headers=PREFER,
    )

    assert intento.status_code in (401, 403), intento.text[:200]
    assert codigo(intento) == "42501"


async def test_un_usuario_no_ve_los_avisos_pausados_de_otro(api, api_otro, payload):
    cuerpo = payload(estado="pausado")
    await crear(api, cuerpo)

    ajeno = await api_otro.get(TABLA, params={"id_externo": f"eq.{cuerpo['id_externo']}"})

    assert ajeno.json() == []


# ── Integridad del esquema ───────────────────────────────────────────────────


async def test_el_id_externo_no_se_repite(api, payload):
    """El unique heredado de ListingMixin: el endpoint genera un UUID por aviso."""
    cuerpo = payload()
    await crear(api, cuerpo)

    repetido = await crear(api, payload(id_externo=cuerpo["id_externo"]))

    assert repetido.status_code == 409, repetido.text[:200]
    assert codigo(repetido) == "23505"


@pytest.mark.parametrize("campo", ["titulo", "url", "id_externo"])
async def test_los_campos_obligatorios_no_admiten_null(api, payload, campo):
    cuerpo = payload()
    del cuerpo[campo]

    respuesta = await crear(api, cuerpo)

    assert respuesta.status_code >= 400, f"{campo} entró como NULL"
    assert codigo(respuesta) == "23502"


async def test_el_aviso_cae_con_la_cuenta(servicio, admin, payload, usuario_efimero):
    """El CASCADE del que depende el borrado de cuenta: sin él quedan avisos huérfanos."""
    cuerpo = payload(usuario_id=usuario_efimero.id)
    await crear(servicio, cuerpo)
    assert len(await leer(servicio, cuerpo["id_externo"])) == 1

    # Con reintento: lo que se prueba aquí es el CASCADE, no la intermitencia de
    # GoTrue. Si el borrado no llega a hacerse, el test no significa nada.
    baja = await reintentar(lambda: admin.delete(f"/admin/users/{usuario_efimero.id}"), intentos=6)
    assert baja.status_code < 400, baja.text[:200]

    assert await leer(servicio, cuerpo["id_externo"]) == []


# ── Caracteres anómalos y basura ─────────────────────────────────────────────


async def test_el_byte_nulo_lo_rechaza_postgres(api, servicio, payload):
    """Un NUL no cabe en una columna de texto de Postgres.

    Sin el saneamiento de la web, cualquiera podría reventar el insert a
    voluntad: el error llega desde la base, no desde una validación nuestra.
    """
    cuerpo = payload(titulo=f"{ETIQUETA} auto\x00roto")

    respuesta = await crear(api, cuerpo)

    assert respuesta.status_code >= 400, respuesta.text[:200]
    assert await leer(servicio, cuerpo["id_externo"]) == []


async def test_los_caracteres_de_control_entran_tal_cual(api, servicio, payload):
    """La base no limpia nada: `normalizar()` de la web es la única defensa."""
    sucio = "linea1\x01\x07\x0b\x1f\x7flinea2"
    cuerpo = payload(descripcion=sucio)

    assert (await crear(api, cuerpo)).status_code == 201

    assert (await leer(servicio, cuerpo["id_externo"]))[0]["descripcion"] == sucio


@pytest.mark.parametrize(
    "ataque",
    [
        "<script>alert(1)</script>",
        '"><img src=x onerror=alert(1)>',
        "javascript:alert(document.cookie)",
        "<svg/onload=alert(1)>",
    ],
)
async def test_el_html_se_guarda_como_texto_plano(api, servicio, payload, ataque):
    """Se guarda literal y vuelve literal: escapar es cosa del render, no del almacenamiento."""
    cuerpo = payload(descripcion=ataque)

    assert (await crear(api, cuerpo)).status_code == 201

    assert (await leer(servicio, cuerpo["id_externo"]))[0]["descripcion"] == ataque


async def test_la_inyeccion_sql_se_guarda_como_texto_y_la_tabla_sigue_viva(api, servicio, payload):
    ataque = "'; DROP TABLE particulares_listings; --"
    cuerpo = payload(marca=ataque)

    assert (await crear(api, cuerpo)).status_code == 201

    assert (await leer(servicio, cuerpo["id_externo"]))[0]["marca"] == ataque
    control = await servicio.get(TABLA, params={"select": "id", "limit": 1})
    assert control.status_code == 200, "la tabla dejó de responder"


async def test_los_operadores_de_postgrest_dentro_de_un_valor_no_alteran_el_filtro(
    api, servicio, payload
):
    """Un valor con sintaxis de PostgREST (`eq.`, comas, `*`) es dato, no consulta."""
    ataque = "eq.Toyota,anio.gt.1900,marca.like.*"
    cuerpo = payload(marca=ataque)
    await crear(api, cuerpo)

    respuesta = await servicio.get(TABLA, params={"marca": f"eq.{ataque}", "select": "id,marca"})

    assert respuesta.status_code == 200, respuesta.text[:200]
    filas = respuesta.json()
    assert len(filas) == 1
    assert filas[0]["marca"] == ataque


@pytest.mark.parametrize(
    "raro",
    [
        "\u202eoduagap etnematcefrep",  # RTL override: invierte lo que se lee
        "invi\u200bsible",  # zero-width space
        "\ufeffcon BOM",
        "Yaris 🚗🔥",
        "cafe\u0301",  # NFD: no es lo mismo que "café" en NFC
    ],
    ids=["rtl", "zero-width", "bom", "emoji", "nfd"],
)
async def test_el_unicode_raro_sobrevive_intacto(api, servicio, payload, raro):
    """Postgres no normaliza: la forma NFC la fija `normalizar()` en la web."""
    cuerpo = payload(modelo=raro)

    assert (await crear(api, cuerpo)).status_code == 201

    assert (await leer(servicio, cuerpo["id_externo"]))[0]["modelo"] == raro


async def test_una_marca_de_101_caracteres_no_entra(api, payload):
    """`marca` es varchar(100): la base sí corta aquí."""
    respuesta = await crear(api, payload(marca="A" * 101))

    assert respuesta.status_code >= 400, respuesta.text[:200]
    assert codigo(respuesta) == "22001"


async def test_un_titulo_larguisimo_si_entra_porque_es_text(api, servicio, payload):
    """El contraste con el test anterior: `titulo` es TEXT y no tiene tope.

    El único límite real es el `max: 100` que aplica `normalizar()` al armar el
    título en el formulario.
    """
    cuerpo = payload(titulo=f"{ETIQUETA} " + "largo " * 3000)

    assert (await crear(api, cuerpo)).status_code == 201

    assert len((await leer(servicio, cuerpo["id_externo"]))[0]["titulo"]) > 10000


@pytest.mark.parametrize(
    "campo,valor",
    [
        ("precio", "abc"),
        ("anio", "dos mil"),
        ("km", 1.5),
        ("disponible", "quizás"),
        ("anio", "2020; DROP TABLE"),
    ],
)
async def test_los_tipos_equivocados_los_rechaza_postgrest(api, payload, campo, valor):
    respuesta = await crear(api, payload(**{campo: valor}))

    assert respuesta.status_code >= 400, f"{campo}={valor!r} entró"
    assert codigo(respuesta) == "22P02"


@pytest.mark.parametrize(
    "campo,valor",
    [
        ("anio", 99999999999),  # Integer de 32 bits
        ("km", 99999999999),
        ("precio", 10**13),  # Numeric(14, 2): como mucho 12 dígitos enteros
    ],
)
async def test_los_numeros_fuera_de_rango_no_entran(api, payload, campo, valor):
    respuesta = await crear(api, payload(**{campo: valor}))

    assert respuesta.status_code >= 400, f"{campo}={valor} entró"
    assert codigo(respuesta) == "22003"


async def test_una_columna_inexistente_tumba_el_insert_entero(api, servicio, payload):
    cuerpo = payload(columna_inventada=1)

    respuesta = await crear(api, cuerpo)

    assert respuesta.status_code == 400, respuesta.text[:200]
    assert codigo(respuesta) == "PGRST204"
    assert await leer(servicio, cuerpo["id_externo"]) == []


# ── Lo que la base NO valida ─────────────────────────────────────────────────
# Los tres tests siguientes afirman el comportamiento actual y dejan el hueco
# documentado: la única barrera es `camposDelFormulario` en la web. Un token
# válido hablando directo con PostgREST se salta las tres cosas.


async def test_la_base_acepta_precio_y_kilometraje_negativos(api, servicio, payload):
    """No existe ningún CHECK: un aviso a -1 peso entra sin chistar."""
    cuerpo = payload(precio=-1, km=-500)

    assert (await crear(api, cuerpo)).status_code == 201

    guardado = (await leer(servicio, cuerpo["id_externo"]))[0]
    assert float(guardado["precio"]) == -1
    assert guardado["km"] == -500


async def test_la_base_acepta_cualquier_estado_que_quepa_en_veinte_caracteres(
    api, servicio, payload
):
    """`ESTADOS_AVISO` vive solo en la web; para Postgres es un varchar(20) cualquiera."""
    cuerpo = payload(estado="basura")

    assert (await crear(api, cuerpo)).status_code == 201
    assert (await leer(servicio, cuerpo["id_externo"]))[0]["estado"] == "basura"

    largo = await crear(api, payload(estado="x" * 21))
    assert codigo(largo) == "22001", "el único límite del estado es su longitud"


async def test_un_usuario_puede_fijarse_las_vistas_y_el_estado_a_mano(api, servicio, payload):
    """La protección contra mass-assignment es la whitelist del endpoint, no la base.

    `camposDelFormulario` solo devuelve las columnas del aviso, así que por la web
    estos campos no son alcanzables; por PostgREST sí.
    """
    cuerpo = payload(vistas=9999, estado="vendido")

    assert (await crear(api, cuerpo)).status_code == 201

    guardado = (await leer(servicio, cuerpo["id_externo"]))[0]
    assert guardado["vistas"] == 9999
    assert guardado["estado"] == "vendido"


async def test_todo_lo_creado_lleva_la_etiqueta(servicio, usuario):
    """Red de seguridad de la propia suite.

    Va al final a propósito: para entonces el usuario de prueba ya creó de todo,
    incluidos los avisos cuyo título y marca son payloads y perdieron el `[TEST]`.
    Si alguno no llevara el prefijo en `id_externo`, el barrido no lo encontraría
    y quedaría vivo en producción.
    """
    respuesta = await servicio.get(
        TABLA, params={"usuario_id": f"eq.{usuario.id}", "select": "id_externo"}
    )

    filas = respuesta.json()
    assert filas, "el usuario de prueba no dejó ningún aviso que revisar"
    sin_etiqueta = [f["id_externo"] for f in filas if not f["id_externo"].startswith(PREFIJO_EXTERNO)]
    assert sin_etiqueta == [], f"avisos fuera del alcance de la limpieza: {sin_etiqueta}"
