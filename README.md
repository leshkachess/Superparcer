# Superparcer

Telegram Mini App для поиска одежды по бренду, размеру, цене, категории и магазинам.

## Быстрый запуск

Требуется Python 3.11+.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
python -m playwright install chromium
Copy-Item .env.example .env
uvicorn app.main:app --reload
```

Откройте `http://127.0.0.1:8000`. Подключены демонстрационный каталог и официальная
поисковая выдача Mercari Japan.

Для запуска Telegram-бота заполните в `.env` новый `TELEGRAM_BOT_TOKEN` и публичный
HTTPS-адрес приложения в `MINI_APP_URL`, затем выполните:

```powershell
python -m app.bot
```

Локальный сервер нужно опубликовать по HTTPS (например, через Cloudflare Tunnel или
ngrok), поскольку Telegram Mini Apps не открывают обычный localhost.

## Добавление магазина

Создайте класс в `app/scrapers/`, унаследуйте его от `BaseScraper`, реализуйте асинхронный
метод `search()` и зарегистрируйте экземпляр в `app/scrapers/__init__.py`. Каждый магазин
нужно подключать с учётом его API, HTML-разметки, robots.txt и условий использования.

Mercari Japan загружает карточки динамически. Адаптер запускает Chromium, читает уже
отрисованный публичный каталог и не обращается напрямую к закрытым API. Он собирает
первую фотографию, название, цену в иенах и прямую ссылку. Результаты кэшируются на
5 минут; лимит и время кэша настраиваются через `.env`.

## Проверка

```powershell
ruff check .
pytest
```

## Railway

В корне проекта находятся `Dockerfile` с Chromium и `railway.toml` с healthcheck.
Railway автоматически передаёт приложению переменную `PORT`.

Для Telegram-бота задайте Railway-переменные `TELEGRAM_BOT_TOKEN` и `MINI_APP_URL`.
При старте приложение автоматически зарегистрирует защищённый webhook по адресу
`/telegram/webhook`; отдельный polling-процесс на Railway не требуется.
