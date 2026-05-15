from decimal import Decimal

from loguru import logger
from sqlalchemy import case, func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from carflip.scrapers.base import AvisoAuto


def _aviso_a_fila(aviso: AvisoAuto) -> dict:
    return {
        "id_externo": aviso.id_externo,
        "url": aviso.url,
        "titulo": aviso.titulo,
        "precio": aviso.precio,
        "moneda": aviso.moneda,
        "marca": aviso.marca,
        "modelo": aviso.modelo,
        "anio": aviso.anio,
        "km": aviso.km,
        "ubicacion": aviso.ubicacion,
        "combustible": aviso.combustible,
        "descripcion": aviso.descripcion,
        "url_imagen": aviso.url_imagen,
        "disponible": aviso.disponible,
        "fecha_publicacion": aviso.fecha_publicacion,
    }


async def upsert_avisos(
    session: AsyncSession,
    avisos: list[AvisoAuto],
    model_class: type,
) -> int:
    """Inserta o actualiza avisos en la tabla correspondiente al scraper.

    Al detectar cambio de precio, guarda el precio anterior y calcula delta_pct.
    Retorna el número de filas afectadas.
    """
    if not avisos:
        return 0

    tabla = model_class.__table__
    vistos: set[str] = set()
    unicos: list[AvisoAuto] = []
    for a in avisos:
        if a.id_externo not in vistos:
            vistos.add(a.id_externo)
            unicos.append(a)
    avisos = unicos
    filas = [_aviso_a_fila(a) for a in avisos]

    stmt = insert(tabla).values(filas)

    precio_cambio = tabla.c.precio != stmt.excluded.precio
    precio_no_nulo = tabla.c.precio.isnot(None)

    stmt = stmt.on_conflict_do_update(
        index_elements=["id_externo"],
        set_={
            "url": stmt.excluded.url,
            "titulo": stmt.excluded.titulo,
            "marca": stmt.excluded.marca,
            "modelo": stmt.excluded.modelo,
            "anio": stmt.excluded.anio,
            "km": stmt.excluded.km,
            "ubicacion": stmt.excluded.ubicacion,
            "combustible": stmt.excluded.combustible,
            "descripcion": stmt.excluded.descripcion,
            "url_imagen": stmt.excluded.url_imagen,
            "disponible": stmt.excluded.disponible,
            "fecha_publicacion": stmt.excluded.fecha_publicacion,
            "moneda": stmt.excluded.moneda,
            "precio_anterior": case(
                (precio_cambio, tabla.c.precio),
                else_=tabla.c.precio_anterior,
            ),
            "delta_pct": case(
                (
                    precio_cambio & precio_no_nulo,
                    (stmt.excluded.precio - tabla.c.precio) / tabla.c.precio * 100,
                ),
                else_=tabla.c.delta_pct,
            ),
            "precio": stmt.excluded.precio,
            "ultima_vez_visto": func.now(),
        },
    )

    resultado = await session.execute(stmt)
    await session.commit()
    n = resultado.rowcount
    logger.debug(f"[uploader] {n} filas upserted en {tabla.name}")
    return n
