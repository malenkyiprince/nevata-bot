"""Vercel + Groq + Tavily. Результат возвращается в том же запросе Mini App."""
import asyncio
import hmac
import json
import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from auth import telegram_user
from config import get_settings
from inflight import Inflight, BusyError, request_key
from research import analyze
from validation import AnalysisError, MAX_PHOTO, MAX_TEXT, prepare_photo, safe_url


ROOT = Path(__file__).resolve().parents[1]


def create_app(settings=None, analyzer=analyze):
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    inflight = Inflight()

    def config():
        return settings or get_settings()

    def user(request):
        current = config()
        if current.preview:
            raise HTTPException(401, "Це перегляд дизайну. Перевірки вимкнені.")
        auth = request.headers.get("authorization", "")
        identity = telegram_user(auth[4:] if auth.startswith("tma ") else "", current.token)
        if not current.permits(identity["id"]):
            raise HTTPException(403, "Власник бота ще не надав доступ до перевірок цьому акаунту.")
        try:
            current.validate()
        except ValueError:
            raise HTTPException(503, "Бот ще не налаштований. Повідом власника.") from None
        return identity, current

    @app.exception_handler(HTTPException)
    async def api_error(request, error):
        return JSONResponse({"error": error.detail}, status_code=error.status_code)

    @app.middleware("http")
    async def security(request, call_next):
        try:
            response = await call_next(request)
        except Exception as error:
            logging.error("Request failed: %s", type(error).__name__)
            response = JSONResponse({"error": "Сервіс тимчасово недоступний."}, status_code=503)
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        elif request.url.path.startswith("/static/") and response.status_code in (200, 304):
            # С query-версией ресурсы безопасно переиспользуются после новых deployment.
            response.headers["Cache-Control"] = "public, max-age=86400"
        else:
            response.headers["Cache-Control"] = "no-cache"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self' https://telegram.org; style-src 'self'; img-src 'self' blob: data:; connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'"
        return response

    @app.get("/")
    async def index():
        return FileResponse(ROOT / "static/index.html")

    @app.get("/health")
    async def health():
        try:
            current = config()
            current.validate()
            return {"status": "ok", "configured": not current.preview, "preview": current.preview}
        except ValueError:
            return {"status": "ok", "configured": False, "preview": False}

    @app.get("/api/session")
    async def session(request: Request):
        identity, current = user(request)
        return {"user": identity, "analysis_timeout": current.timeout}

    @app.post("/api/analyze")
    async def check(request: Request):
        identity, current = user(request)
        if request.headers.get("content-type", "").split(";")[0] != "multipart/form-data":
            raise HTTPException(400, "Використай форму застосунку.")
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > MAX_PHOTO + 65536:
                raise HTTPException(413, "Фото має бути до 3 МБ.")
        request._body = bytes(body)
        del body
        try:
            async with request.form(max_files=1, max_fields=2, max_part_size=MAX_TEXT * 4) as form:
                if set(form) - {"kind", "text", "photo"} or len(form.multi_items()) != len(form):
                    raise ValueError
                kind, text = form.get("kind"), form.get("text", "")
                if not isinstance(text, str) or not isinstance(kind, str):
                    raise ValueError
                text = text.strip()
                photo = None
                if "photo" in form:
                    if not hasattr(form["photo"], "read"):
                        raise ValueError
                    photo = await form["photo"].read(MAX_PHOTO + 1)
                if kind not in {"text", "link", "photo"} or len(text) > MAX_TEXT:
                    raise ValueError
                if (kind == "photo" and not photo) or (kind != "photo" and (not text or photo)):
                    raise ValueError
                if kind == "link" and not safe_url(text):
                    raise ValueError
                if photo:
                    photo = await asyncio.to_thread(prepare_photo, photo)
        except (ValueError, TypeError, AttributeError):
            raise HTTPException(400, "Додай коректний текст, посилання або фото JPEG/PNG/WebP до 3 МБ.") from None
        try:
            key = request_key(identity["id"], kind, text, photo)
            return await inflight.run(key, lambda: analyzer(current, kind, text, photo))
        except BusyError:
            raise HTTPException(503, "Зараз багато перевірок. Спробуй трохи пізніше; новий API-запит не запускався.") from None
        except AnalysisError as error:
            raise HTTPException(502, str(error)) from None

    @app.post("/api/telegram")
    async def webhook(request: Request):
        current = config()
        secret = request.headers.get("x-telegram-bot-api-secret-token", "")
        if not current.webhook_secret or not hmac.compare_digest(secret.encode(), current.webhook_secret.encode()):
            raise HTTPException(403, "Forbidden")
        raw = await request.body()
        if len(raw) > 65536:
            raise HTTPException(413, "Payload too large")
        try:
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise ValueError
        except ValueError:
            raise HTTPException(400, "Invalid update") from None
        message = data.get("message")
        if not isinstance(message, dict):
            return {"ok": True}
        chat, sender = message.get("chat"), message.get("from")
        if not isinstance(chat, dict) or type(chat.get("id")) is not int or chat.get("type") != "private":
            return {"ok": True}
        sender = sender if isinstance(sender, dict) else {}
        if sender.get("is_bot"):
            return {"ok": True}
        identity = sender.get("id", chat["id"])
        command = message.get("text")
        command = command.split("@")[0] if isinstance(command, str) else ""
        text = f"Твій Telegram ID: {identity}" if command == "/id" else (
            "🔥 Привіт! Це Бавовна. Відкрий застосунок, щоб перевірити текст, посилання або фото.\n\n"
            "Пошук виконує Tavily, аналіз — Groq. Матеріал передається цим сервісам. Історія зберігається на твоєму пристрої.")
        # Быстрый webhook не запускает платный анализ и не требует очереди.
        return {"method": "sendMessage", "chat_id": chat["id"], "text": text,
                "reply_markup": {"inline_keyboard": [[{"text": "🔎 Відкрити Бавовну", "web_app": {"url": current.app_url}}]]}}

    app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
    return app


app = create_app()
