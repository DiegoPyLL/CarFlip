"""
Utilidades para procesamiento de imágenes — conversión a AVIF.
"""

from pathlib import Path

from loguru import logger


def convertir_a_avif(ruta: Path, calidad: int = 60, destino: Path | None = None) -> Path | None:
	"""
	Convierte una imagen a AVIF.
	Si `destino` es un directorio, guarda el AVIF ahí y conserva el original.
	Si `destino` es None, guarda junto al original y lo elimina si la extensión cambia.
	Retorna la ruta al archivo AVIF, o None si falla.
	"""
	from PIL import Image

	ruta_avif = (destino / ruta.with_suffix(".avif").name) if destino else ruta.with_suffix(".avif")
	try:
		with Image.open(ruta) as img:
			img.convert("RGB").save(ruta_avif, "AVIF", quality=calidad)
		if destino is None and ruta.suffix.lower() != ".avif":
			ruta.unlink(missing_ok=True)
		logger.debug(f"Imagen convertida a AVIF: {ruta_avif.name}")
		return ruta_avif
	except Exception as e:
		logger.warning(f"No se pudo convertir imagen a AVIF {ruta.name}: {e}")
		return None
