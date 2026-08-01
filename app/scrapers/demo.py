from app.models import ClothingType, Product, SearchFilters
from app.scrapers.base import BaseScraper


class DemoScraper(BaseScraper):
    source_id = "demo"
    source_name = "Демо-магазин"

    _products = [
        Product(
            source=source_name,
            title="Nike Sportswear Club Hoodie",
            brand="Nike",
            sizes=["S", "M", "L", "XL"],
            price=8490,
            clothing_type=ClothingType.HOODIE,
            url="https://example.com/nike-hoodie",
            image_url="https://placehold.co/600x800/18181b/ffffff?text=Nike+Hoodie",
        ),
        Product(
            source=source_name,
            title="Levi's 501 Original",
            brand="Levi's",
            sizes=["28", "30", "32", "34"],
            price=10990,
            clothing_type=ClothingType.JEANS,
            url="https://example.com/levis-501",
            image_url="https://placehold.co/600x800/1e3a5f/ffffff?text=Levis+501",
        ),
        Product(
            source=source_name,
            title="Adidas Samba OG",
            brand="Adidas",
            sizes=["40", "41", "42", "43"],
            price=13990,
            clothing_type=ClothingType.SHOES,
            url="https://example.com/adidas-samba",
            image_url="https://placehold.co/600x800/e5e5e5/111111?text=Adidas+Samba",
        ),
    ]

    async def search(self, filters: SearchFilters) -> list[Product]:
        result: list[Product] = []
        for product in self._products:
            if filters.brand and filters.brand.casefold() not in (product.brand or "").casefold():
                continue
            if filters.size and filters.size.casefold() not in {
                size.casefold() for size in product.sizes
            }:
                continue
            if filters.price_from is not None and product.price < filters.price_from:
                continue
            if filters.price_to is not None and product.price > filters.price_to:
                continue
            if filters.clothing_type and product.clothing_type != filters.clothing_type:
                continue
            result.append(product)
        return result

