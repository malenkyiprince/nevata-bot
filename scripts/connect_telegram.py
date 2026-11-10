# coding: utf-8
"""Подключение Telegram стандартной библиотекой Python: pip не нужен."""
import json
import os
import re
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]


def read_env():
    values = {}
    for line in (ROOT / '.env').read_text(encoding='utf-8').splitlines():
        key, sep, value = line.strip().partition('=')
        if sep and not key.startswith('#'):
            values[key.strip()] = value.strip().strip('\"\'')
    values.update(os.environ)
    return values


def request_json(url, payload=None):
    request = Request(url, data=json.dumps(payload).encode() if payload is not None else None,
                      headers={'Content-Type': 'application/json'})
    with urlopen(request, timeout=25) as response:
        return json.loads(response.read(1024 * 1024))


def main():
    values = read_env()
    token = values.get('TELEGRAM_BOT_TOKEN', '')
    base = values.get('APP_URL', '').rstrip('/')
    secret = values.get('TELEGRAM_WEBHOOK_SECRET', '')
    parsed = urlsplit(base)
    if not token or parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.path or parsed.query or parsed.fragment or not re.fullmatch(r'[A-Za-z0-9_-]{32,256}', secret):
        raise ValueError('Заполни токен, APP_URL без пути и секрет webhook в .env.')
    health = request_json(base + '/health')
    if not health.get('configured') or health.get('preview'):
        raise ValueError('Deployment ещё не настроен. Проверь переменные Vercel и сделай Redeploy.')

    def telegram(method, **payload):
        data = request_json('https://api.telegram.org/bot' + token + '/' + method, payload)
        if not data.get('ok'):
            raise ValueError('Telegram не подтвердил ' + method + '. Проверь настройки.')
        return data['result']

    telegram('getMe')
    telegram('setWebhook', url=base + '/api/telegram', secret_token=secret,
             allowed_updates=['message'], drop_pending_updates=False)
    telegram('setChatMenuButton', menu_button={'type': 'web_app', 'text': 'Відкрити Бавовну', 'web_app': {'url': base}})
    if telegram('getWebhookInfo').get('url') != base + '/api/telegram':
        raise ValueError('Адрес webhook не совпал с APP_URL.')
    print('Telegram подключён к', base)
    print('Отправь /start и нажми кнопку. Команда /id покажет твой Telegram ID.')


if __name__ == '__main__':
    try:
        main()
    except (URLError, TimeoutError, OSError):
        raise SystemExit('Нет связи или файла .env. Проверь настройки и доступность deployment. Секреты не выводятся.') from None
    except (ValueError, KeyError, TypeError) as error:
        raise SystemExit(str(error) if isinstance(error, ValueError) and not isinstance(error, json.JSONDecodeError) else 'Некорректный ответ сервиса.') from None
