import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl

from fastapi import HTTPException


def telegram_user(init_data, token, *, now=None):
    """Доверяем только подписанному initData, никогда — user_id из браузера."""
    try:
        if not init_data or len(init_data) > 8192:
            raise ValueError
        pairs = parse_qsl(init_data, keep_blank_values=True, strict_parsing=True)
        data = dict(pairs)
        if len(data) != len(pairs):
            raise ValueError
        received = data.pop("hash")
        secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
        check = "\n".join(f"{key}={value}" for key, value in sorted(data.items()))
        expected = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, received):
            raise ValueError
        age = (time.time() if now is None else now) - int(data["auth_date"])
        user = json.loads(data["user"])
        if not -30 <= age <= 3600 or type(user["id"]) is not int or not 0 < user["id"] < 2**63:
            raise ValueError
        return {"id": user["id"], "first_name": str(user.get("first_name", ""))[:64]}
    except (KeyError, ValueError, TypeError, UnicodeError):
        raise HTTPException(status_code=401, detail="Відкрий застосунок заново через кнопку в Telegram.") from None
