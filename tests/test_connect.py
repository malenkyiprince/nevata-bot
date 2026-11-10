import importlib.util
import io
import contextlib
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("connect", Path(__file__).resolve().parents[1] / "scripts/connect_telegram.py")
connect = importlib.util.module_from_spec(spec)
spec.loader.exec_module(connect)


class ConnectTests(unittest.TestCase):
    def test_connect_preserves_pending_updates_and_sets_correct_webapp(self):
        values = {"TELEGRAM_BOT_TOKEN": "test", "APP_URL": "https://app.example.org", "TELEGRAM_WEBHOOK_SECRET": "s" * 40}
        responses = [{"configured": True, "preview": False}, {"ok": True, "result": {}},
            {"ok": True, "result": True}, {"ok": True, "result": True},
            {"ok": True, "result": {"url": "https://app.example.org/api/telegram"}}]
        with patch.object(connect, "read_env", return_value=values), patch.object(connect, "request_json", side_effect=responses) as request, contextlib.redirect_stdout(io.StringIO()):
            connect.main()
        self.assertFalse(request.call_args_list[2].args[1]["drop_pending_updates"])
        self.assertEqual(request.call_args_list[3].args[1]["menu_button"]["web_app"]["url"], values["APP_URL"])

    def test_unconfigured_deployment_never_changes_telegram(self):
        values = {"TELEGRAM_BOT_TOKEN": "test", "APP_URL": "https://app.example.org", "TELEGRAM_WEBHOOK_SECRET": "s" * 40}
        with patch.object(connect, "read_env", return_value=values), patch.object(connect, "request_json", return_value={"configured": False}) as request:
            with self.assertRaises(ValueError): connect.main()
        self.assertEqual(request.call_count, 1)
