from datetime import datetime
from pathlib import Path

from loguru import logger

from carflip.scrapers.base import AvisoAuto


def exportar_markdown(
    avisos: list[AvisoAuto],
    titulo: str,
    ruta_destino: Path,
) -> Path:
    """Exporta una lista de avisos a un archivo Markdown.

    Args:
        avisos: Lista de avisos a exportar
        titulo: Título del documento
        ruta_destino: Carpeta donde guardar el archivo

    Returns:
        Path al archivo generado
    """
    ruta_destino = Path(ruta_destino)
    ruta_destino.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    nombre_archivo = f"{titulo.lower().replace(' ', '_')}_{timestamp}.md"
    ruta_archivo = ruta_destino / nombre_archivo

    contenido = _construir_contenido(avisos, titulo)

    ruta_archivo.write_text(contenido, encoding="utf-8")
    logger.info(f"Markdown exportado: {ruta_archivo}")

    return ruta_archivo


def _construir_contenido(avisos: list[AvisoAuto], titulo: str) -> str:
    """Construye el contenido Markdown."""
    fecha = datetime.now().strftime("%d/%m/%Y %H:%M")
    lineas = [
        f"# {titulo} — {fecha}\n",
        f"**Total:** {len(avisos)} avisos\n",
        "---\n",
    ]

    for aviso in avisos:
        lineas.extend(_aviso_a_markdown(aviso))

    return "\n".join(lineas)


def _aviso_a_markdown(aviso: AvisoAuto) -> list[str]:
    """Convierte un aviso a formato Markdown."""
    lineas = [
        f"\n## {aviso.titulo}\n",
        "| Campo | Valor |",
        "|---|---|",
    ]

    if aviso.precio:
        precio_fmt = f"${aviso.precio:,.0f}" if aviso.precio >= 1 else str(aviso.precio)
        lineas.append(f"| Precio | {precio_fmt} {aviso.moneda} |")

    if aviso.marca:
        lineas.append(f"| Marca | {aviso.marca} |")

    if aviso.modelo:
        lineas.append(f"| Modelo | {aviso.modelo} |")

    if aviso.anio:
        lineas.append(f"| Año | {aviso.anio} |")

    if aviso.km is not None:
        lineas.append(f"| Kilometraje | {aviso.km:,} km |")

    if aviso.combustible:
        lineas.append(f"| Combustible | {aviso.combustible} |")

    if aviso.ubicacion:
        lineas.append(f"| Ubicación | {aviso.ubicacion} |")

    lineas.extend([
        f"\n[Ver aviso]({aviso.url})\n",
        "---",
    ])

    return lineas
