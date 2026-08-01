import asyncio

from app.models import SearchFilters
from app.scrapers import scraper_registry
from app.scrapers.mercari import MercariJPScraper
from app.services import search_products


def test_search_filters_demo_products() -> None:
    result = asyncio.run(
        search_products(
            SearchFilters(brand="nike", size="M", price_to=9000, sources=["demo"]),
            scraper_registry(),
        )
    )
    assert len(result.products) == 1
    assert result.products[0].brand == "Nike"


def test_unknown_source_is_reported() -> None:
    result = asyncio.run(
        search_products(SearchFilters(sources=["missing"]), scraper_registry())
    )
    assert result.products == []
    assert result.errors == {"missing": "Неизвестный источник"}


def test_mercari_builds_filtered_official_search_link() -> None:
    scraper = MercariJPScraper()
    filters = SearchFilters(
        brand="Nike",
        size="M",
        price_from=1000,
        price_to=10000,
        clothing_type="Худи",
        sources=["mercari_jp"],
    )
    url = str(scraper.search_link(filters).url)
    assert "keyword=Nike+M+%E3%83%91%E3%83%BC%E3%82%AB%E3%83%BC" in url
    assert "price_min=1000" in url
    assert "price_max=10000" in url
    assert "status=on_sale" in url


def test_mercari_normalizes_rendered_cards() -> None:
    scraper = MercariJPScraper()
    products = scraper._normalize(
        [{
            "href": "https://jp.mercari.com/item/m123?source=search",
            "text": "Nike hoodie ¥8,400",
            "aria": "Nike hoodieの画像 8,400円 €48.00",
            "image": "https://static.mercdn.net/item/detail/orig/photos/m123.jpg",
            "alt": "Nike hoodieの画像",
        }],
        SearchFilters(brand="Nike", size="M", sources=["mercari_jp"]),
        24,
    )
    assert len(products) == 1
    assert products[0].title == "Nike hoodie"
    assert products[0].price == 8400
    assert products[0].currency == "JPY"
