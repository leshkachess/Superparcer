from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    telegram_bot_token: str = ""
    mini_app_url: str = "http://localhost:8000"
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    mercari_max_items: int = 24
    mercari_cache_seconds: int = 300
    mercari_headless: bool = True

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    return Settings()
