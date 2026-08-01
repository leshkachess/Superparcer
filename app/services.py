import asyncio

from app.models import Product, SearchFilters, SearchResponse
from app.scrapers import BaseScraper


async def search_products(
    filters: SearchFilters, registry: dict[str, BaseScraper]
) -> SearchResponse:
    selected = {key: registry[key] for key in filters.sources if key in registry}
    unknown = set(filters.sources) - set(selected)
    errors = {key: "Неизвестный источник" for key in unknown}

    results = await asyncio.gather(
        *(scraper.search(filters) for scraper in selected.values()),
        return_exceptions=True,
    )
    products: list[Product] = []
    source_links = []
    for (source_id, _), result in zip(selected.items(), results, strict=True):
        if isinstance(result, BaseException):
            errors[source_id] = "Источник временно недоступен"
        else:
            products.extend(result)

    for scraper in selected.values():
        link = scraper.search_link(filters)
        if link:
            source_links.append(link)

    products.sort(key=lambda product: product.price)
    return SearchResponse(products=products, errors=errors, source_links=source_links)
