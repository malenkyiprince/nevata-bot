"""Создать .env с секретом, сохранив любой существующий файл."""
import os
from pathlib import Path
import secrets


root = Path(__file__).resolve().parents[1]
content = (root / ".env.example").read_text(encoding="utf-8")
content = content.replace("TELEGRAM_WEBHOOK_SECRET=\n", "TELEGRAM_WEBHOOK_SECRET=" + secrets.token_urlsafe(32) + "\n")
try:
    descriptor = os.open(root / ".env", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
except FileExistsError:
    raise SystemExit(".env уже существует. Файл оставлен без изменений.")
with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
    stream.write(content)
print("Создан", root / ".env")
print("Заполни токен Telegram, ключи Groq и Tavily и APP_URL. Секрет webhook уже создан.")
