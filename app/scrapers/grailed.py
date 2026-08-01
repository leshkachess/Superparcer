import asyncio
import re
import time
import unicodedata

from app.browser import browser_semaphore
from app.config import get_settings
from app.enrichment import translate_text_to_russian
from app.models import ClothingType, Product, SearchFilters, SourceSearchLink
from app.scrapers.base import BaseScraper
from app.sizing import format_size, shoe_size_options

try:
    from playwright.async_api import TimeoutError as PlaywrightTimeoutError
    from playwright.async_api import async_playwright
except ImportError:  # pragma: no cover
    async_playwright = None
    PlaywrightTimeoutError = TimeoutError


_cache: dict[str, tuple[float, list[Product]]] = {}
_cache_lock = asyncio.Lock()


class GrailedScraper(BaseScraper):
    source_id = "grailed"
    source_name = "Grailed"
    base_url = "https://www.grailed.com"
    page_size = 24

    _category_paths = {
        ClothingType.T_SHIRT: "short-sleeve-t-shirts",
        ClothingType.HOODIE: "sweatshirts-hoodies",
        ClothingType.JACKET: "outerwear",
        ClothingType.TROUSERS: "casual-pants",
        ClothingType.JEANS: "denim",
        ClothingType.SHOES: "footwear",
        ClothingType.ACCESSORY: "accessories",
    }
    _category_keywords = {
        ClothingType.T_SHIRT: ("t-shirt", "tee", "shirt"),
        ClothingType.HOODIE: ("hoodie", "sweatshirt", "hooded"),
        ClothingType.JACKET: ("jacket", "coat", "bomber", "parka", "outerwear"),
        ClothingType.TROUSERS: ("pants", "trousers", "slacks", "joggers"),
        ClothingType.JEANS: ("jeans", "denim pants"),
        ClothingType.SHOES: (
            "shoes", "sneaker", "boots", "sandals", "loafer", "heels", "slip on",
        ),
        ClothingType.ACCESSORY: (
            "bag", "belt", "glasses", "gloves", "scarf", "hat", "cap", "jewelry",
            "watch", "wallet", "sunglasses", "necklace", "bracelet", "ring", "tie",
        ),
    }

    async def search(self, filters: SearchFilters) -> list[Product]:
        url = str(self.search_link(filters).url)
        cache_key = f"{url}#page={filters.page}#min={filters.price_from}#max={filters.price_to}"
        settings = get_settings()
        cached = _cache.get(cache_key)
        if cached and time.monotonic() - cached[0] < settings.mercari_cache_seconds:
            return cached[1]
        if async_playwright is None:
            raise RuntimeError("Playwright не установлен")

        async with _cache_lock:
            cached = _cache.get(cache_key)
            if cached and time.monotonic() - cached[0] < settings.mercari_cache_seconds:
                return cached[1]
            async with browser_semaphore:
                products = await self._collect(url, filters)
            descriptions = await asyncio.gather(
                *(translate_text_to_russian(product.title, "en") for product in products)
            )
            for product, description in zip(products, descriptions, strict=True):
                product.title = f"{product.brand} — {description}" if product.brand else description
            _cache[cache_key] = (time.monotonic(), products)
            return products

    async def _collect(self, url: str, filters: SearchFilters) -> list[Product]:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(
                headless=get_settings().mercari_headless,
                args=["--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"],
            )
            try:
                page = await browser.new_page(
                    locale="en-US",
                    viewport={"width": 1280, "height": 900},
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/136.0.0.0 Safari/537.36"
                    ),
                )
                await page.add_init_script(
                    "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
                )
                await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                try:
                    await page.wait_for_selector('a[href*="/listings/"]', timeout=25_000)
                except PlaywrightTimeoutError as exc:
                    raise RuntimeError("Grailed не отдал карточки товаров") from exc

                target = filters.page * self.page_size * 5
                previous = 0
                stagnant = 0
                for _ in range(max(6, filters.page * 12)):
                    await page.mouse.wheel(0, 1600)
                    await page.wait_for_timeout(700)
                    count = await page.locator('a[href*="/listings/"]').count()
                    stagnant = stagnant + 1 if count == previous else 0
                    previous = count
                    if count >= target or stagnant >= 3:
                        break

                raw_items = await page.locator('a[href*="/listings/"]').evaluate_all(
                    """
                    (links) => links.map((link) => {
                      const card = link.parentElement;
                      return {
                        href: link.href,
                        designer: link.querySelector('[class*="UserItem_designer__"]')?.textContent || '',
                        title: link.querySelector('[class*="UserItem_title"]')?.textContent || '',
                        size: link.querySelector('[class*="UserItem_size__"]')?.textContent || '',
                        price: card?.querySelector('[data-testid="Current"]')?.textContent || '',
                        image: link.querySelector('img')?.currentSrc || link.querySelector('img')?.src || ''
                      };
                    })
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
        offset = (filters.page - 1) * self.page_size
        category_page = filters.clothing_type is not None

        for item in raw_items:
            url = item.get("href", "").split("?")[0]
            if not url or url in seen:
                continue
            seen.add(url)
            designer = item.get("designer", "").strip()
            title = item.get("title", "").strip()
            title = self._strip_designer_prefix(title, designer)
            price_match = re.search(r"\$\s*([\d,.]+)", item.get("price", ""))
            if not title or not price_match:
                continue
            price = float(price_match.group(1).replace(",", ""))
            if filters.brand and self._normalize_text(filters.brand) not in self._normalize_text(designer):
                continue
            if filters.size:
                listed_size = item.get("size", "").strip().casefold().replace(",", ".")
                display_size = item.get("size", "").strip()
                if filters.clothing_type == ClothingType.SHOES:
                    options = shoe_size_options(filters.size)
                    normalized_listed = listed_size.removeprefix("us ").removeprefix("eu ")
                    matched = next(
                        (
                            option
                            for option in options
                            if normalized_listed == format_size(option.us)
                        ),
                        None,
                    )
                    if matched is None:
                        continue
                    display_size = f"EU {format_size(matched.eu)}"
                elif filters.size.casefold() != listed_size:
                    continue
            else:
                display_size = item.get("size", "").strip()
            if filters.clothing_type and not category_page:
                if not any(
                    keyword in title.casefold()
                    for keyword in self._category_keywords[filters.clothing_type]
                ):
                    continue
            if filters.price_from is not None and price < filters.price_from:
                continue
            if filters.price_to is not None and price > filters.price_to:
                continue
            if offset:
                offset -= 1
                continue

            products.append(
                Product(
                    source=self.source_name,
                    title=title,
                    brand=designer,
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
        if filters.brand and filters.clothing_type:
            slug = self._slug(filters.brand)
            category = self._category_paths[filters.clothing_type]
            url = f"{self.base_url}/designers/{slug}/{category}"
        elif filters.clothing_type:
            url = f"{self.base_url}/categories/{self._category_paths[filters.clothing_type]}"
        elif filters.brand:
            slug = self._slug(filters.brand)
            url = f"{self.base_url}/designers/{slug}"
        else:
            url = f"{self.base_url}/shop"
        return SourceSearchLink(
            source=self.source_name,
            url=url,
            note="Открыть публичный каталог Grailed.",
        )

    @staticmethod
    def _normalize_text(value: str) -> str:
        return re.sub(r"[^a-z0-9]", "", value.casefold())

    @staticmethod
    def _slug(value: str) -> str:
        ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
        return re.sub(r"[^a-z0-9]+", "-", ascii_value.casefold()).strip("-")

    @staticmethod
    def _strip_designer_prefix(title: str, designer: str) -> str:
        if not designer:
            return title
        stripped = re.sub(
            rf"^\s*{re.escape(designer)}\s*(?:[-—×x]\s*)?",
            "",
            title,
            flags=re.IGNORECASE,
        ).strip()
        return stripped or title
