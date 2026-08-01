import asyncio
import re
import time
from urllib.parse import urlencode

from app.config import get_settings
from app.enrichment import convert_jpy_products_to_usd, translate_product_titles_to_russian
from app.models import ClothingType, Product, SearchFilters, SourceSearchLink
from app.scrapers.base import BaseScraper

try:
    from playwright.async_api import TimeoutError as PlaywrightTimeoutError
    from playwright.async_api import async_playwright
except ImportError:  # pragma: no cover - produces a useful runtime error without extras
    async_playwright = None
    PlaywrightTimeoutError = TimeoutError


_cache: dict[str, tuple[float, list[Product]]] = {}
_browser_lock = asyncio.Lock()


class MercariJPScraper(BaseScraper):
    """Collect product cards rendered on Mercari's public search page."""

    source_id = "mercari_jp"
    source_name = "Mercari Japan"
    base_url = "https://jp.mercari.com/search"

    _category_terms = {
        ClothingType.T_SHIRT: "Tシャツ",
        ClothingType.HOODIE: "パーカー",
        ClothingType.JACKET: "ジャケット",
        ClothingType.TROUSERS: "パンツ",
        ClothingType.JEANS: "ジーンズ",
        ClothingType.SHOES: "靴",
        ClothingType.ACCESSORY: "アクセサリー",
    }

    _brand_aliases = {
        "nike": ("nike", "ナイキ"),
        "adidas": ("adidas", "アディダス"),
        "uniqlo": ("uniqlo", "ユニクロ"),
        "levis": ("levis", "levi's", "リーバイス"),
        "supreme": ("supreme", "シュプリーム"),
        "stussy": ("stussy", "ステューシー"),
        "stoneisland": ("stone island", "ストーンアイランド"),
        "newbalance": ("new balance", "ニューバランス"),
        "puma": ("puma", "プーマ"),
        "gucci": ("gucci", "グッチ"),
        "prada": ("prada", "プラダ"),
    }

    _category_keywords = {
        ClothingType.T_SHIRT: ("tシャツ", "tee", "t-shirt", "ティーシャツ"),
        ClothingType.HOODIE: ("パーカー", "hoodie", "hooded", "フーディ"),
        ClothingType.JACKET: ("ジャケット", "ブルゾン", "コート", "jacket", "coat"),
        ClothingType.TROUSERS: ("パンツ", "スラックス", "trousers", "pants"),
        ClothingType.JEANS: ("ジーンズ", "デニムパンツ", "jeans"),
        ClothingType.SHOES: (
            "スニーカー",
            "シューズ",
            "ブーツ",
            "サンダル",
            "ローファー",
            "パンプス",
            "shoes",
            "sneaker",
            "boots",
        ),
        ClothingType.ACCESSORY: (
            "アクセサリー",
            "ネックレス",
            "ブレスレット",
            "リング",
            "ベルト",
            "帽子",
            "accessory",
            "necklace",
            "bracelet",
        ),
    }

    async def search(self, filters: SearchFilters) -> list[Product]:
        url = str(self.search_link(filters).url)
        settings = get_settings()
        cached = _cache.get(url)
        if cached and time.monotonic() - cached[0] < settings.mercari_cache_seconds:
            return cached[1]
        if async_playwright is None:
            raise RuntimeError("Playwright не установлен: pip install -e .")

        async with _browser_lock:
            cached = _cache.get(url)
            if cached and time.monotonic() - cached[0] < settings.mercari_cache_seconds:
                return cached[1]
            products = await self._collect(url, filters)
            await asyncio.gather(
                convert_jpy_products_to_usd(products),
                translate_product_titles_to_russian(products),
            )
            _cache[url] = (time.monotonic(), products)
            return products

    async def _collect(self, url: str, filters: SearchFilters) -> list[Product]:
        settings = get_settings()
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(
                headless=settings.mercari_headless,
                args=["--disable-dev-shm-usage"],
            )
            try:
                page = await browser.new_page(
                    locale="ja-JP",
                    viewport={"width": 1280, "height": 900},
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/136.0.0.0 Safari/537.36"
                    ),
                )
                await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                try:
                    await page.wait_for_selector('a[href*="/item/"]', timeout=20_000)
                except PlaywrightTimeoutError as exc:
                    raise RuntimeError("Mercari не отдал карточки товаров") from exc

                for _ in range(4):
                    await page.mouse.wheel(0, 1400)
                    await page.wait_for_timeout(700)

                raw_items = await page.locator('a[href*="/item/"]').evaluate_all(
                    """
                    (links) => links.map((link) => {
                      const image = link.querySelector('img') || link.parentElement?.querySelector('img');
                      const thumbnail = link.querySelector('[role="img"][aria-label]');
                      return {
                        href: link.href,
                        text: link.innerText || link.textContent || '',
                        aria: thumbnail?.getAttribute('aria-label') || link.getAttribute('aria-label') || '',
                        image: image?.currentSrc || image?.src || '',
                        alt: image?.alt || ''
                      };
                    })
                    """
                )
            finally:
                await browser.close()

        return self._normalize(raw_items, filters, settings.mercari_max_items)

    def _normalize(
        self, raw_items: list[dict[str, str]], filters: SearchFilters, limit: int
    ) -> list[Product]:
        products: list[Product] = []
        seen: set[str] = set()
        for item in raw_items:
            url = item.get("href", "").split("?")[0]
            if not url or url in seen:
                continue
            text = " ".join(item.get("text", "").split())
            combined = " ".join((text, item.get("aria", ""), item.get("alt", "")))
            price_match = re.search(
                r"(?:(?:¥|￥)\s*([\d,]+)|([\d,]+)\s*円)", combined
            )
            if not price_match:
                continue
            raw_price = price_match.group(1) or price_match.group(2)
            price = int(raw_price.replace(",", ""))
            title = item.get("alt", "").strip()
            title = re.sub(r"の(?:サムネイル|画像).*$", "", title).strip()
            if not title:
                title = re.sub(r"(?:現在\s*)?[¥￥]\s*[\d,]+", "", text).strip()
            if not title:
                title = item.get("aria", "").strip() or "Товар Mercari"

            if filters.brand and not self._matches_brand(title, filters.brand):
                continue
            if filters.clothing_type and not self._matches_category(title, filters.clothing_type):
                continue

            seen.add(url)
            products.append(
                Product(
                    source=self.source_name,
                    title=title,
                    brand=filters.brand,
                    sizes=[filters.size] if filters.size else [],
                    price=price,
                    currency="JPY",
                    clothing_type=filters.clothing_type,
                    url=url,
                    image_url=item.get("image") or None,
                )
            )
            if len(products) >= limit:
                break
        return products

    @classmethod
    def _matches_brand(cls, title: str, brand: str) -> bool:
        normalized_brand = re.sub(r"[^a-zа-яё0-9]", "", brand.casefold())
        aliases = cls._brand_aliases.get(normalized_brand, (brand,))
        folded_title = title.casefold()
        return any(
            re.search(rf"(?<![a-z0-9]){re.escape(alias.casefold())}(?![a-z0-9])", folded_title)
            for alias in aliases
        )

    @classmethod
    def _matches_category(cls, title: str, category: ClothingType) -> bool:
        folded_title = title.casefold()
        if category == ClothingType.JEANS and any(
            word in folded_title for word in ("ジャケット", "jacket", "バッグ", "bag")
        ):
            return False
        return any(word in folded_title for word in cls._category_keywords[category])

    def search_link(self, filters: SearchFilters) -> SourceSearchLink:
        terms = [filters.brand, filters.size]
        if filters.clothing_type:
            terms.append(self._category_terms[filters.clothing_type])

        params: dict[str, str | int] = {
            "keyword": " ".join(term for term in terms if term),
            "status": "on_sale",
        }
        if filters.price_from is not None:
            params["price_min"] = filters.price_from
        if filters.price_to is not None:
            params["price_max"] = filters.price_to

        return SourceSearchLink(
            source=self.source_name,
            url=f"{self.base_url}?{urlencode(params)}",
            note="Открыть полную официальную выдачу Mercari.",
        )
