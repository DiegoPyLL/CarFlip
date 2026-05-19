"""
Utilidades para procesamiento de imágenes — conversión a AVIF.
"""

from pathlib import Path

from loguru import logger


def convertir_a_avif(ruta: Path, calidad: int = 60) -> Path | None:
	"""
	Convierte una imagen a AVIF. Elimina el original si la extensión cambia.
	Retorna la ruta al archivo AVIF, o None si falla.
	"""
	from PIL import Image

	ruta_avif = ruta.with_suffix(".avif")
	try:
		with Image.open(ruta) as img:
			img.convert("RGB").save(ruta_avif, "AVIF", quality=calidad)
		if ruta.suffix.lower() != ".avif":
			ruta.unlink(missing_ok=True)
		logger.debug(f"Imagen convertida a AVIF: {ruta_avif.name}")
		return ruta_avif
	except Exception as e:
		logger.warning(f"No se pudo convertir imagen a AVIF {ruta.name}: {e}")
		return None
