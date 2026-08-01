import asyncio
import re
import time

import httpx

from app.models import Product

_rate_cache: tuple[float, float] | None = None
_rate_lock = asyncio.Lock()
_translation_cache: dict[str, str] = {}
_translation_semaphore = asyncio.Semaphore(6)


async def convert_jpy_products_to_usd(
    products: list[Product], rate: float | None = None
) -> None:
    rate = rate or await get_jpy_usd_rate()
    if rate is None:
        return
    for product in products:
        if product.currency != "JPY":
            continue
        product.original_price = product.price
        product.original_currency = product.currency
        product.price = round(product.price * rate, 2)
        product.currency = "USD"


async def get_jpy_usd_rate() -> float | None:
    global _rate_cache
    if _rate_cache and time.monotonic() - _rate_cache[0] < 3600:
        return _rate_cache[1]
    async with _rate_lock:
        if _rate_cache and time.monotonic() - _rate_cache[0] < 3600:
            return _rate_cache[1]
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                response = await client.get("https://api.frankfurter.dev/v2/rate/JPY/USD")
                response.raise_for_status()
                rate = float(response.json()["rate"])
        except (httpx.HTTPError, KeyError, TypeError, ValueError):
            return None
        _rate_cache = (time.monotonic(), rate)
        return rate


def cached_jpy_usd_rate() -> float | None:
    if _rate_cache and time.monotonic() - _rate_cache[0] < 3600:
        return _rate_cache[1]
    return None


async def translate_product_titles_to_russian(products: list[Product]) -> None:
    translated = await asyncio.gather(*(_translate_title(product.title) for product in products))
    for product, title in zip(products, translated, strict=True):
        product.title = title


async def _translate_title(title: str) -> str:
    if not re.search(r"[\u3040-\u30ff\u3400-\u9fff]", title):
        return title
    if title in _translation_cache:
        return _translation_cache[title]
    async with _translation_semaphore:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(
                    "https://translate.googleapis.com/translate_a/single",
                    params={"client": "gtx", "sl": "ja", "tl": "ru", "dt": "t", "q": title},
                )
                response.raise_for_status()
                result = "".join(part[0] for part in response.json()[0] if part[0]).strip()
        except (httpx.HTTPError, IndexError, KeyError, TypeError, ValueError):
            return title
        if "パーカー" in title:
            result = re.sub(r"\bпарк(?:а|и|у|ой|е)?\b", "худи", result, flags=re.IGNORECASE)
        _translation_cache[title] = result or title
        return _translation_cache[title]
