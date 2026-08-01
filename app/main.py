import hashlib
from contextlib import asynccontextmanager
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.types import Update
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.models import SearchFilters, SearchResponse, SourceInfo
from app.bot import router as bot_router
from app.config import get_settings
from app.scrapers import scraper_registry
from app.services import search_products

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    if not settings.telegram_bot_token:
        app.state.telegram_bot = None
        yield
        return

    bot = Bot(settings.telegram_bot_token)
    dispatcher = Dispatcher()
    dispatcher.include_router(bot_router)
    webhook_secret = hashlib.sha256(settings.telegram_bot_token.encode()).hexdigest()
    webhook_url = f"{settings.mini_app_url.rstrip('/')}/telegram/webhook"
    await bot.set_webhook(
        webhook_url,
        secret_token=webhook_secret,
        allowed_updates=dispatcher.resolve_used_update_types(),
    )
    app.state.telegram_bot = bot
    app.state.telegram_dispatcher = dispatcher
    app.state.telegram_webhook_secret = webhook_secret
    try:
        yield
    finally:
        await bot.session.close()


app = FastAPI(title="Superparcer API", version="0.1.0", lifespan=lifespan)
registry = scraper_registry()


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/telegram/webhook", include_in_schema=False)
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict[str, bool]:
    bot = request.app.state.telegram_bot
    if bot is None:
        raise HTTPException(status_code=503, detail="Telegram bot is not configured")
    if x_telegram_bot_api_secret_token != request.app.state.telegram_webhook_secret:
        raise HTTPException(status_code=403, detail="Invalid webhook secret")
    update = Update.model_validate(await request.json(), context={"bot": bot})
    await request.app.state.telegram_dispatcher.feed_update(bot, update)
    return {"ok": True}


@app.get("/api/sources", response_model=list[SourceInfo])
async def sources() -> list[SourceInfo]:
    return [
        SourceInfo(id=scraper.source_id, name=scraper.source_name)
        for scraper in registry.values()
    ]


@app.post("/api/search", response_model=SearchResponse)
async def search(filters: SearchFilters) -> SearchResponse:
    return await search_products(filters, registry)


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
