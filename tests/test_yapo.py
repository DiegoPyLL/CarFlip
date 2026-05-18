import asyncio
from carflip.scrapers.Yapo.yapoCloud import ScraperYapoCloud

async def main():
    print("Iniciando prueba local de Yapo Cloud...")
    scraper = ScraperYapoCloud()
    
    # Llamamos a scrape() directamente, saltándonos la carga a la base de datos
    avisos = await scraper.scrape()
    
    print(f"\n¡Éxito! Se obtuvieron {len(avisos)} avisos válidos:")
    for aviso in avisos:
        print(f"- {aviso.titulo} | Precio: ${aviso.precio} | KM: {aviso.km}")

if __name__ == "__main__":
    asyncio.run(main())
