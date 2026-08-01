from abc import ABC, abstractmethod

from app.models import Product, SearchFilters, SourceSearchLink


class BaseScraper(ABC):
    source_id: str
    source_name: str

    @abstractmethod
    async def search(self, filters: SearchFilters) -> list[Product]:
        """Return normalized products matching filters."""

    def search_link(self, filters: SearchFilters) -> SourceSearchLink | None:
        """Return an official filtered search URL when listings cannot be ingested."""
        return None
