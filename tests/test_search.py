import asyncio

from app.models import SearchFilters
from app.scrapers import scraper_registry
from app.scrapers.grailed import GrailedScraper
from app.scrapers.mercari import MercariJPScraper
from app.services import search_products
from app.sizing import shoe_size_options


def test_registry_contains_only_real_stores() -> None:
    assert set(scraper_registry()) == {"mercari_jp", "grailed"}


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
        price_from=10,
        price_to=100,
        clothing_type="Худи",
        sources=["mercari_jp"],
    )
    url = str(scraper._search_link(filters, 0.00625).url)
    assert "keyword=Nike+M+%E3%83%91%E3%83%BC%E3%82%AB%E3%83%BC" in url
    assert "price_min=1600" in url
    assert "price_max=16000" in url
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


def test_mercari_strictly_filters_brand_and_category() -> None:
    scraper = MercariJPScraper()
    raw = [
        {
            "href": "https://jp.mercari.com/item/m1",
            "text": "¥4,000",
            "aria": "ナイキ パーカーの画像 4,000円",
            "image": "https://example.com/1.jpg",
            "alt": "ナイキ パーカーのサムネイル",
        },
        {
            "href": "https://jp.mercari.com/item/m2",
            "text": "¥3,000",
            "aria": "Adidas パーカーの画像 3,000円",
            "image": "https://example.com/2.jpg",
            "alt": "Adidas パーカーのサムネイル",
        },
        {
            "href": "https://jp.mercari.com/item/m3",
            "text": "¥5,000",
            "aria": "Nike スニーカーの画像 5,000円",
            "image": "https://example.com/3.jpg",
            "alt": "Nike スニーカーのサムネイル",
        },
    ]
    products = scraper._normalize(
        raw,
        SearchFilters(brand="Nike", clothing_type="Худи", sources=["mercari_jp"]),
        24,
    )
    assert [product.title for product in products] == ["ナイキ パーカー"]


def test_mercari_pagination_skips_previous_products() -> None:
    scraper = MercariJPScraper()
    raw = [
        {
            "href": f"https://jp.mercari.com/item/m{index}",
            "text": f"¥{index * 1000}",
            "aria": f"Item {index} {index * 1000}円",
            "image": f"https://example.com/{index}.jpg",
            "alt": f"Item {index}のサムネイル",
        }
        for index in range(1, 4)
    ]
    products = scraper._normalize(
        raw, SearchFilters(sources=["mercari_jp"], page=2), limit=2, offset=2
    )
    assert [product.title for product in products] == ["Item 3"]


def test_grailed_normalizes_and_filters_cards_in_usd() -> None:
    scraper = GrailedScraper()
    raw = [
        {
            "href": "https://www.grailed.com/listings/1-nike-cap",
            "designer": "Nike",
            "title": "Logo Cap",
            "size": "OS",
            "price": "$45",
            "image": "https://media-assets.grailed.com/cap.jpg",
        },
        {
            "href": "https://www.grailed.com/listings/2-nike-belt",
            "designer": "Nike",
            "title": "Logo Belt",
            "size": "OS",
            "price": "$120",
            "image": "https://media-assets.grailed.com/belt.jpg",
        },
    ]
    products = scraper._normalize(
        raw,
        SearchFilters(
            brand="Nike",
            clothing_type="Аксессуар",
            price_from=20,
            price_to=60,
            sources=["grailed"],
        ),
    )
    assert len(products) == 1
    assert products[0].title == "Logo Cap"
    assert products[0].price == 45
    assert products[0].currency == "USD"
    assert scraper._strip_designer_prefix("Nike Logo Cap", "Nike") == "Logo Cap"


def test_eu_shoe_size_expands_to_half_size_cm_and_us() -> None:
    options = shoe_size_options("44")
    assert [(size.eu, size.cm, size.us) for size in options] == [
        (44, 28, 10),
        (44.5, 28.5, 10.5),
    ]


def test_mercari_matches_eu_cm_and_us_shoe_sizes() -> None:
    scraper = MercariJPScraper()
    assert scraper._matches_shoe_size("Nike sneakers 28cm", "44")
    assert scraper._matches_shoe_size("Nike sneakers US 10.5", "44")
    assert scraper._matches_shoe_size("Nike sneakers EU44.5", "44")
    assert not scraper._matches_shoe_size("Nike sneakers 27cm", "44")
