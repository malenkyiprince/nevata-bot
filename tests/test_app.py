import hashlib
import hmac
import io
import json
import time
import unittest
from urllib.parse import urlencode
import httpx
from PIL import Image
from api.index import create_app
from config import Settings

def settings():
    return Settings(token="test:telegram", key="test-groq", search_key="test-tavily", app_url="https://app.example.org", webhook_secret="s" * 40)


def signed(config, user_id=10, expired=False):
    data = {"auth_date": str(int(time.time()) - (4000 if expired else 0)), "user": json.dumps({"id": user_id, "first_name": "Тест"})}
    secret = hmac.new(b"WebAppData", config.token.encode(), hashlib.sha256).digest()
    check = "\n".join(f"{key}={value}" for key, value in sorted(data.items()))
    data["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return {"Authorization": "tma " + urlencode(data)}


class AppTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.config, self.calls = settings(), []
        async def fake_analyze(config, kind, text, photo):
            self.calls.append((kind, text, photo))
            return {"score":25,"segments":[{"text":"Перевірено"}],"sources":[],"limited":False}
        self.app = create_app(self.config, fake_analyze)
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="https://app.example.org")

    async def asyncTearDown(self): await self.client.aclose()

    async def submit(self, kind="text", text="Матеріал", photo=None, headers=None):
        files = {"kind": (None, kind), "text": (None, text)}
        if photo is not None: files["photo"] = ("photo.png", photo, "image/png")
        return await self.client.post("/api/analyze", files=files, headers=headers or signed(self.config))

    async def test_one_submission_returns_final_result_without_queue(self):
        response = await self.submit()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["score"], 25)
        self.assertEqual(len(self.calls), 1)

    async def test_private_api_requires_signed_fresh_telegram_data(self):
        self.assertEqual((await self.client.get("/api/session")).status_code, 401)
        self.assertEqual((await self.client.get("/api/session", headers=signed(self.config, expired=True))).status_code, 401)
        self.assertEqual((await self.client.get("/api/session", headers=signed(self.config))).status_code, 200)

    async def test_optional_allowlist_protects_paid_analysis(self):
        self.config.allowed_users = "20,30"
        self.assertEqual((await self.submit()).status_code, 403)
        self.assertFalse(self.calls)
        self.assertEqual((await self.submit(headers=signed(self.config, 20))).status_code, 200)

    async def test_preview_never_calls_paid_provider(self):
        self.config.preview = True
        self.assertEqual((await self.submit()).status_code, 401)
        self.assertFalse(self.calls)

    async def test_photo_is_validated_and_prepared(self):
        data = io.BytesIO()
        Image.new("RGBA", (20, 20), (0, 0, 0, 0)).save(data, "PNG")
        response = await self.submit(kind="photo", photo=data.getvalue())
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(self.calls[0][2].startswith(b"\xff\xd8"))

    async def test_bad_input_is_rejected_before_model_call(self):
        for values in ({"text": ""}, {"text": "x" * 4001}, {"kind": "link", "text": "javascript:alert(1)"},
                       {"kind": "photo", "photo": b"not a photo"}):
            self.assertEqual((await self.submit(**values)).status_code, 400)
        self.assertFalse(self.calls)

    async def test_oversized_upload_is_rejected(self):
        response = await self.submit(kind="photo", photo=b"x" * (3 * 1024 * 1024 + 65536))
        self.assertEqual(response.status_code, 413)
        self.assertFalse(self.calls)

    async def test_webhook_only_opens_mini_app_and_never_analyzes(self):
        update = {"update_id": 1, "message": {"text": "Матеріал", "from": {"id": 10}, "chat": {"id": 10, "type": "private"}}}
        headers = {"X-Telegram-Bot-Api-Secret-Token": self.config.webhook_secret}
        response = await self.client.post("/api/telegram", json=update, headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["method"], "sendMessage")
        self.assertEqual(response.json()["reply_markup"]["inline_keyboard"][0][0]["web_app"]["url"], self.config.app_url)
        self.assertFalse(self.calls)
        self.assertEqual((await self.client.post("/api/telegram", json=update)).status_code, 403)

    async def test_id_command_and_no_server_side_history(self):
        update = {"message": {"text": "/id", "from": {"id": 123}, "chat": {"id": 123, "type": "private"}}}
        response = await self.client.post("/api/telegram", json=update, headers={"X-Telegram-Bot-Api-Secret-Token": self.config.webhook_secret})
        self.assertIn("123", response.json()["text"])
        self.assertEqual((await self.client.get("/api/history", headers=signed(self.config))).status_code, 404)

    async def test_static_assets_and_health(self):
        self.assertEqual((await self.client.get("/")).status_code, 200)
        self.assertEqual((await self.client.get("/static/app.js")).status_code, 200)
        self.assertTrue((await self.client.get("/health")).json()["configured"])
