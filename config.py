"""Все настройки в одном месте. Платные резервные провайдеры не используются."""
import os
import re
from functools import lru_cache
from dataclasses import dataclass
from urllib.parse import urlsplit

from dotenv import load_dotenv


@dataclass
class Settings:
    token: str = ""
    key: str = ""
    search_key: str = ""
    app_url: str = ""
    webhook_secret: str = ""
    model: str = "openai/gpt-oss-120b"
    vision_model: str = "qwen/qwen3.8-27b"
    timeout: int = 180
    max_tokens: int = 3200
    allowed_users: str = ""
    preview: bool = False

    @classmethod
    def from_env(cls):
        load_dotenv()
        return cls(token=os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
            key=os.getenv("GROQ_API_KEY", "").strip(), search_key=os.getenv("TAVILY_API_KEY", "").strip(),
            app_url=os.getenv("APP_URL", "").strip().rstrip("/"),
            webhook_secret=os.getenv("TELEGRAM_WEBHOOK_SECRET", "").strip(),
            timeout=int(os.getenv("ANALYSIS_TIMEOUT", "180")),
            allowed_users=os.getenv("ALLOWED_TELEGRAM_IDS", "").strip(), preview=os.getenv("PREVIEW", "0") == "1")

    def validate(self):
        if self.preview:
            return
        if not all((self.token, self.key, self.search_key, self.app_url, self.webhook_secret)):
            raise ValueError("Заполни TELEGRAM_BOT_TOKEN, GROQ_API_KEY, TAVILY_API_KEY, APP_URL и TELEGRAM_WEBHOOK_SECRET.")
        url = urlsplit(self.app_url)
        if url.scheme != "https" or not url.hostname or url.username or url.query or url.fragment or url.path not in ("", "/"):
            raise ValueError("APP_URL должен быть HTTPS-адресом без пути и параметров.")
        if not re.fullmatch(r"[A-Za-z0-9_-]{32,256}", self.webhook_secret):
            raise ValueError("Секрет webhook: 32–256 букв, цифр, _ или -.")
        if not 30 <= self.timeout <= 220:
            raise ValueError("ANALYSIS_TIMEOUT: от 30 до 220 секунд.")
        if self.allowed_users and not re.fullmatch(r"\d+(?:\s*,\s*\d+)*", self.allowed_users):
            raise ValueError("ALLOWED_TELEGRAM_IDS: числовые ID через запятую.")

    def permits(self, user_id):
        return not self.allowed_users or str(user_id) in {value.strip() for value in self.allowed_users.split(",")}


@lru_cache(maxsize=1)
def get_settings():
    """Переменные Vercel меняются через redeploy, читать .env на каждом запросе не нужно."""
    return Settings.from_env()
