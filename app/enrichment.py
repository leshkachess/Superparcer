import asyncio
import re
import time

import httpx

from app.models import Product

_rate_cache: tuple[float, float] | None = None
_rate_lock = asyncio.Lock()
_translation_cache: dict[tuple[str, str], str] = {}
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
    translated = await asyncio.gather(
        *(translate_text_to_russian(product.title, "ja") for product in products)
    )
    for product, title in zip(products, translated, strict=True):
        product.title = title


async def translate_text_to_russian(text: str, source_language: str) -> str:
    if source_language == "ja" and not re.search(r"[\u3040-\u30ff\u3400-\u9fff]", text):
        return text
    cache_key = (source_language, text)
    if cache_key in _translation_cache:
        return _translation_cache[cache_key]
    async with _translation_semaphore:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(
                    "https://translate.googleapis.com/translate_a/single",
                    params={
                        "client": "gtx",
                        "sl": source_language,
                        "tl": "ru",
                        "dt": "t",
                        "q": text,
                    },
                )
                response.raise_for_status()
                result = "".join(part[0] for part in response.json()[0] if part[0]).strip()
        except (httpx.HTTPError, IndexError, KeyError, TypeError, ValueError):
            return text
        if "パーカー" in text:
            result = re.sub(r"\bпарк(?:а|и|у|ой|е)?\b", "худи", result, flags=re.IGNORECASE)
        _translation_cache[cache_key] = result or text
        return _translation_cache[cache_key]
