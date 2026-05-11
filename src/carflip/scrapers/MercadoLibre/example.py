"""
Ejemplo de uso del cliente MercadoLibre de forma independiente.

Para ejecutar:
    python example.py --max 10

Requiere dependencias instaladas:
    pip install -r requirements.txt
"""

import asyncio
import sys
from pathlib import Path

# Asegura que pueda importar desde la raíz del proyecto
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from mercadolibre import MercadoLibreClient
from carflip.config import settings


async def main(max_avisos: int = 50) -> None:
    """Obtiene autos y motos de MercadoLibre e imprime un resumen."""
    print(f"📡 Conectando a MercadoLibre API (máx {max_avisos} por categoría)...\n")

    async with MercadoLibreClient() as client:
        resultados = await client.fetch_todo(max_por_categoria=max_avisos)

    autos = resultados["autos"]
    motos = resultados["motos"]

    print(f"\n✅ Autos obtenidos: {len(autos)}")
    print(f"✅ Motos obtenidas: {len(motos)}\n")

    # Mostrar primeros 3 autos como ejemplo
    print("=" * 80)
    print("AUTOS (primeros 3)")
    print("=" * 80)
    for aviso in autos[:3]:
        print(f"\n🚗 {aviso.titulo}")
        print(f"   Precio:   ${aviso.precio:,.0f} {aviso.moneda}" if aviso.precio else "   Precio:   No especificado")
        print(f"   Marca:    {aviso.marca or 'N/A'}")
        print(f"   Modelo:   {aviso.modelo or 'N/A'}")
        print(f"   Año:      {aviso.anio or 'N/A'}")
        print(f"   KM:       {aviso.km:,}" if aviso.km else "   KM:       N/A")
        print(f"   Ubicación: {aviso.ubicacion or 'N/A'}")
        print(f"   Enlace:   {aviso.url}")

    # Mostrar primeras 3 motos como ejemplo
    print("\n" + "=" * 80)
    print("MOTOS (primeras 3)")
    print("=" * 80)
    for aviso in motos[:3]:
        print(f"\n🏍️  {aviso.titulo}")
        print(f"   Precio:   ${aviso.precio:,.0f} {aviso.moneda}" if aviso.precio else "   Precio:   No especificado")
        print(f"   Marca:    {aviso.marca or 'N/A'}")
        print(f"   Modelo:   {aviso.modelo or 'N/A'}")
        print(f"   Año:      {aviso.anio or 'N/A'}")
        print(f"   Ubicación: {aviso.ubicacion or 'N/A'}")
        print(f"   Enlace:   {aviso.url}")

    print("\n" + "=" * 80)
    print(f"\n✨ Total: {len(autos)} autos + {len(motos)} motos")
    print(f"📁 Output dir configurado: {settings.output_dir}")


if __name__ == "__main__":
    max_avisos = 50
    if len(sys.argv) > 1:
        try:
            max_avisos = int(sys.argv[1])
        except ValueError:
            print(f"❌ Parámetro inválido. Uso: python example.py [número]")
            sys.exit(1)

    # Otra forma de pasar parámetro: --max 10
    if "--max" in sys.argv:
        idx = sys.argv.index("--max")
        if idx + 1 < len(sys.argv):
            try:
                max_avisos = int(sys.argv[idx + 1])
            except ValueError:
                pass

    asyncio.run(main(max_avisos))
