import asyncio
import logging

from aiogram import Bot, Dispatcher, Router
from aiogram.filters import CommandStart
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup, WebAppInfo

from app.config import get_settings

router = Router()


@router.message(CommandStart())
async def start(message: Message) -> None:
    settings = get_settings()
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text="Найти одежду",
                    web_app=WebAppInfo(url=settings.mini_app_url),
                )
            ]
        ],
        resize_keyboard=True,
    )
    await message.answer(
        "Выбери фильтры — я найду подходящие вещи в магазинах.",
        reply_markup=keyboard,
    )


async def main() -> None:
    settings = get_settings()
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is missing")
    logging.basicConfig(level=logging.INFO)
    dispatcher = Dispatcher()
    dispatcher.include_router(router)
    async with Bot(settings.telegram_bot_token) as bot:
        await dispatcher.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

