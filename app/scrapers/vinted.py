import asyncio
import re
import time
from urllib.parse import urlencode

from app.browser import browser_semaphore
from app.config import get_settings
from app.enrichment import translate_text_to_russian
from app.models import ClothingType, Product, SearchFilters, SourceSearchLink
from app.scrapers.base import BaseScraper
from app.sizing import format_size, shoe_size_options, women_us_size

try:
    from playwright.async_api import TimeoutError as PlaywrightTimeoutError
    from playwright.async_api import async_playwright
except ImportError:  # pragma: no cover
    async_playwright = None
    PlaywrightTimeoutError = TimeoutError


_cache: dict[str, tuple[float, list[Product]]] = {}
_cache_lock = asyncio.Lock()


class VintedScraper(BaseScraper):
    source_id = "vinted"
    source_name = "Vinted"
    base_url = "https://www.vinted.com/catalog"
    page_size = 24
    site_page_size = 96

    _category_terms = {
        ClothingType.T_SHIRT: "t-shirt",
        ClothingType.HOODIE: "hoodie sweatshirt",
        ClothingType.JACKET: "jacket coat",
        ClothingType.TROUSERS: "pants trousers",
        ClothingType.JEANS: "jeans denim",
        ClothingType.SHOES: "shoes sneakers",
        ClothingType.ACCESSORY: "accessories bag belt hat jewelry wallet",
    }

    async def search(self, filters: SearchFilters) -> list[Product]:
        url = str(self.search_link(filters).url)
        cached = _cache.get(url)
        ttl = get_settings().mercari_cache_seconds
        if cached and time.monotonic() - cached[0] < ttl:
            return cached[1]
        if async_playwright is None:
            raise RuntimeError("Playwright не установлен")

        async with _cache_lock:
            cached = _cache.get(url)
            if cached and time.monotonic() - cached[0] < ttl:
                return cached[1]
            async with browser_semaphore:
                products = await self._collect(url, filters)
            translated = await asyncio.gather(
                *(translate_text_to_russian(product.title, "en") for product in products)
            )
            for product, title in zip(products, translated, strict=True):
                product.title = f"{product.brand} — {title}" if product.brand else title
            _cache[url] = (time.monotonic(), products)
            return products

    async def _collect(self, url: str, filters: SearchFilters) -> list[Product]:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(
                headless=get_settings().mercari_headless,
                args=["--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"],
            )
            try:
                page = await browser.new_page(locale="en-US")
                await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                try:
                    await page.wait_for_selector('a[href*="/items/"]', timeout=25_000)
                except PlaywrightTimeoutError as exc:
                    raise RuntimeError("Vinted не отдал карточки товаров") from exc
                raw_items = await page.locator('a[href*="/items/"]').evaluate_all(
                    """
                    (links) => links.map((link) => ({
                      href: link.href,
                      metadata: link.getAttribute('title') || '',
                      image: link.parentElement?.querySelector('img')?.currentSrc ||
                             link.parentElement?.querySelector('img')?.src || ''
                    }))
                    """
                )
            finally:
                await browser.close()
        return self._normalize(raw_items, filters)

    def _normalize(
        self, raw_items: list[dict[str, str]], filters: SearchFilters
    ) -> list[Product]:
        products: list[Product] = []
        seen: set[str] = set()
        offset = ((filters.page - 1) * self.page_size) % self.site_page_size
        for item in raw_items:
            url = item.get("href", "").split("?")[0]
            metadata = item.get("metadata", "")
            if not url or url in seen:
                continue
            seen.add(url)
            price_match = re.search(r", ([\d,.]+) \$, [\d,.]+ \$$", metadata)
            if not price_match:
                continue
            price = float(price_match.group(1).replace(",", ""))
            brand_match = re.search(r", Brand: (.*?), Condition:", metadata)
            brand = brand_match.group(1).strip() if brand_match else None
            title_end = brand_match.start() if brand_match else metadata.find(", Condition:")
            title = metadata[:title_end].strip() if title_end >= 0 else ""
            size_match = re.search(r", Size: (.*?), [\d,.]+ \$,", metadata)
            listed_size = size_match.group(1).strip() if size_match else ""

            if filters.brand and self._normalize_text(filters.brand) not in self._normalize_text(brand or ""):
                continue
            display_size = listed_size
            if filters.size:
                if filters.clothing_type == ClothingType.SHOES:
                    matched = self._match_shoe_size(listed_size, filters.size)
                    if matched is None:
                        continue
                    display_size = f"EU {format_size(matched.eu)}"
                elif filters.size.casefold() not in listed_size.casefold():
                    continue
            if filters.price_from is not None and price < filters.price_from:
                continue
            if filters.price_to is not None and price > filters.price_to:
                continue
            if offset:
                offset -= 1
                continue

            title = self._strip_brand_prefix(title, brand or "")
            products.append(
                Product(
                    source=self.source_name,
                    title=title,
                    brand=brand,
                    sizes=[display_size] if display_size else [],
                    price=price,
                    currency="USD",
                    clothing_type=filters.clothing_type,
                    url=url,
                    image_url=item.get("image") or None,
                )
            )
            if len(products) >= self.page_size:
                break
        return products

    def search_link(self, filters: SearchFilters) -> SourceSearchLink:
        terms = [filters.brand]
        if filters.clothing_type:
            terms.append(self._category_terms[filters.clothing_type])
        absolute_offset = (filters.page - 1) * self.page_size
        params: dict[str, str | int | float] = {
            "search_text": " ".join(term for term in terms if term),
            "currency": "USD",
            "page": absolute_offset // self.site_page_size + 1,
        }
        if filters.price_from is not None:
            params["price_from"] = filters.price_from
        if filters.price_to is not None:
            params["price_to"] = filters.price_to
        return SourceSearchLink(
            source=self.source_name,
            url=f"{self.base_url}?{urlencode(params)}",
            note="Открыть публичный каталог Vinted.",
        )

    @staticmethod
    def _match_shoe_size(listed: str, eu_input: str):
        normalized = listed.casefold().replace(",", ".").strip()
        number_match = re.search(r"\d+(?:\.\d+)?", normalized)
        if not number_match:
            return None
        value = number_match.group(0)
        for option in shoe_size_options(eu_input):
            if "eu" in normalized and value == format_size(option.eu):
                return option
            if "cm" in normalized and value == format_size(option.cm):
                return option
            women_us = women_us_size(option.eu)
            if "eu" not in normalized and "cm" not in normalized:
                if value in {format_size(option.us), format_size(women_us) if women_us else ""}:
                    return option
        return None

    @staticmethod
    def _normalize_text(value: str) -> str:
        return re.sub(r"[^a-z0-9]", "", value.casefold())

    @staticmethod
    def _strip_brand_prefix(title: str, brand: str) -> str:
        if not brand:
            return title
        stripped = re.sub(
            rf"^\s*{re.escape(brand)}\s*(?:[-—×x]\s*)?",
            "",
            title,
            flags=re.IGNORECASE,
        ).strip()
        return stripped or title
