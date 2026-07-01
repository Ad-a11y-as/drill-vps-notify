import json
import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vmiss_notify.config import AppConfig
from vmiss_notify.notifier import MessageApiError, MessageNotifier, UrllibJsonTransport


class FakeClock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now


class FakeTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def post_json(self, url, payload, headers=None):
        self.calls.append({"url": url, "payload": payload, "headers": headers or {}})
        return self.responses.pop(0)


class FakeResponse:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return None

    def read(self):
        return self.body.encode("utf-8")


def make_config():
    return AppConfig(
        vmiss_email="user@example.com",
        vmiss_password="secret",
        store_url="https://app.vmiss.com/store/us-los-angeles-cn2",
        target_product="US.LA.CN2.Basic",
        check_interval_seconds=30,
        headless=False,
        user_data_dir=Path(".browser-profile"),
        login_url="https://app.vmiss.com/login",
        cloudflare_wait_seconds=900,
        message_cloud_domain="notify.example.com",
        message_app_id="app-id",
        message_app_secret="app-secret",
        message_permanent_code="permanent-code",
        message_to_users=["user1", "user2"],
        token_refresh_after_seconds=6600,
    )


class MessageNotifierTest(unittest.TestCase):
    def test_send_text_fetches_token_then_sends_message(self):
        transport = FakeTransport(
            [
                {"errorCode": 0, "corpAccessToken": "token-1", "corpId": "corp-1", "expiresIn": 7200},
                {"errorCode": 0, "traceId": "trace-1", "errorMessage": "OK"},
            ]
        )
        notifier = MessageNotifier(make_config(), transport=transport, clock=FakeClock(1000))

        notifier.send_text("VMISS 有货")

        self.assertEqual(len(transport.calls), 2)
        self.assertTrue(
            transport.calls[0]["url"].startswith(
                "https://notify.example.com/cgi/corpAccessToken/get/V2?thirdTraceId="
            )
        )
        self.assertEqual(
            transport.calls[0]["payload"],
            {"appId": "app-id", "appSecret": "app-secret", "permanentCode": "permanent-code"},
        )
        self.assertTrue(transport.calls[1]["url"].startswith("https://notify.example.com/cgi/message/send?thirdTraceId="))
        self.assertEqual(transport.calls[1]["headers"], {})
        self.assertEqual(
            transport.calls[1]["payload"],
            {
                "toUser": ["user1", "user2"],
                "msgType": "text",
                "text": {"content": "VMISS 有货"},
                "accessToken": "token-1",
                "corpId": "corp-1",
            },
        )

    def test_send_text_reuses_token_before_6600_seconds(self):
        clock = FakeClock(1000)
        transport = FakeTransport(
            [
                {"errorCode": 0, "corpAccessToken": "token-1", "corpId": "corp-1", "expiresIn": 7200},
                {"errorCode": 0},
                {"errorCode": 0},
            ]
        )
        notifier = MessageNotifier(make_config(), transport=transport, clock=clock)

        notifier.send_text("first")
        clock.now = 7599
        notifier.send_text("second")

        token_calls = [call for call in transport.calls if "/cgi/corpAccessToken/get/V2" in call["url"]]
        self.assertEqual(len(token_calls), 1)
        self.assertEqual(transport.calls[-1]["payload"]["accessToken"], "token-1")

    def test_send_text_renews_token_at_6600_seconds(self):
        clock = FakeClock(1000)
        transport = FakeTransport(
            [
                {"errorCode": 0, "corpAccessToken": "token-1", "corpId": "corp-1", "expiresIn": 7200},
                {"errorCode": 0},
                {"errorCode": 0, "corpAccessToken": "token-2", "corpId": "corp-1", "expiresIn": 7200},
                {"errorCode": 0},
            ]
        )
        notifier = MessageNotifier(make_config(), transport=transport, clock=clock)

        notifier.send_text("first")
        clock.now = 7600
        notifier.send_text("second")

        token_calls = [call for call in transport.calls if "/cgi/corpAccessToken/get/V2" in call["url"]]
        self.assertEqual(len(token_calls), 2)
        self.assertEqual(transport.calls[-1]["payload"]["accessToken"], "token-2")

    def test_send_text_renews_early_when_expires_in_is_shorter_than_6600_seconds(self):
        clock = FakeClock(1000)
        transport = FakeTransport(
            [
                {"errorCode": 0, "corpAccessToken": "token-1", "corpId": "corp-1", "expiresIn": 120},
                {"errorCode": 0},
                {"errorCode": 0, "corpAccessToken": "token-2", "corpId": "corp-1", "expiresIn": 7200},
                {"errorCode": 0},
            ]
        )
        notifier = MessageNotifier(make_config(), transport=transport, clock=clock)

        notifier.send_text("first")
        clock.now = 1060
        notifier.send_text("second")

        token_calls = [call for call in transport.calls if "/cgi/corpAccessToken/get/V2" in call["url"]]
        self.assertEqual(len(token_calls), 2)
        self.assertEqual(transport.calls[-1]["payload"]["accessToken"], "token-2")

    def test_send_text_raises_when_api_returns_non_zero_error_code(self):
        transport = FakeTransport(
            [{"errorCode": 123, "errorMessage": "bad credentials", "errorDescription": "failed"}]
        )
        notifier = MessageNotifier(make_config(), transport=transport, clock=FakeClock(1000))

        with self.assertRaises(MessageApiError) as exc_info:
            notifier.send_text("hello")

        self.assertIn("123", str(exc_info.exception))
        self.assertIn("bad credentials", str(exc_info.exception))


class UrllibJsonTransportLoggingTest(unittest.TestCase):
    def test_post_json_prints_full_request_and_response(self):
        transport = UrllibJsonTransport()
        stdout = io.StringIO()

        with patch(
            "vmiss_notify.notifier.request.urlopen",
            return_value=FakeResponse('{"errorCode": 0, "corpAccessToken": "token-1"}'),
        ):
            with redirect_stdout(stdout):
                transport.post_json(
                    "https://notify.example.com/cgi/corpAccessToken/get/V2?thirdTraceId=trace-1",
                    {"appId": "app-id", "appSecret": "secret-value", "permanentCode": "perm-value"},
                    headers={"corpAccessToken": "token-header", "corpId": "corp-1"},
                )

        output = stdout.getvalue()
        self.assertIn("https://notify.example.com/cgi/corpAccessToken/get/V2?thirdTraceId=trace-1", output)
        self.assertIn('"appSecret": "secret-value"', output)
        self.assertIn('"permanentCode": "perm-value"', output)
        self.assertIn('"corpAccessToken": "token-header"', output)
        self.assertIn('"corpAccessToken": "token-1"', output)


if __name__ == "__main__":
    unittest.main()
