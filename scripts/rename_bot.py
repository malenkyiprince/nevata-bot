"""Обновить отображаемое имя Telegram. Токен, username и webhook не меняются."""
import sys
from urllib.error import URLError
from urllib.parse import urlsplit

from connect_telegram import read_env, request_json


def main():
    values = read_env()
    token = values.get("TELEGRAM_BOT_TOKEN", "")
    base = values.get("APP_URL", "").rstrip("/")
    if not token:
        raise ValueError("Заполни TELEGRAM_BOT_TOKEN в .env.")
    parsed = urlsplit(base)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.path or parsed.query or parsed.fragment:
        raise ValueError("Перевір APP_URL у .env.")
    for language, name in (("", "NeVata"), ("en", "NeVata"), ("uk", "НеВата")):
        data = request_json("https://api.telegram.org/bot" + token + "/setMyName", {"name": name, "language_code": language})
        if not data.get("ok"):
            raise ValueError("Telegram не підтвердив перейменування. Перевір токен і повтори команду.")
    data = request_json("https://api.telegram.org/bot" + token + "/setChatMenuButton",
        {"menu_button": {"type": "web_app", "text": "Відкрити НеВату", "web_app": {"url": base}}})
    if not data.get("ok"):
        raise ValueError("Не вдалося оновити назву кнопки меню.")
    print("Ім’я Telegram оновлено: НеВата (uk), NeVata (en та інші мови).")


if __name__ == "__main__":
    try:
        main()
    except (URLError, OSError, ValueError):
        sys.exit("Не вдалося змінити ім’я Telegram. Перевір .env і з’єднання; токен не виводиться.")
