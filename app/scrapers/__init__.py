from app.scrapers.base import BaseScraper
from app.scrapers.demo import DemoScraper
from app.scrapers.mercari import MercariJPScraper


def scraper_registry() -> dict[str, BaseScraper]:
    scrapers: list[BaseScraper] = [MercariJPScraper(), DemoScraper()]
    return {scraper.source_id: scraper for scraper in scrapers}


__all__ = ["BaseScraper", "scraper_registry"]
