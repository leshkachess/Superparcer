from app.scrapers.base import BaseScraper
from app.scrapers.grailed import GrailedScraper
from app.scrapers.mercari import MercariJPScraper


def scraper_registry() -> dict[str, BaseScraper]:
    scrapers: list[BaseScraper] = [MercariJPScraper(), GrailedScraper()]
    return {scraper.source_id: scraper for scraper in scrapers}


__all__ = ["BaseScraper", "scraper_registry"]
