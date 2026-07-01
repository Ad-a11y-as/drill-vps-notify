import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vmiss_notify.browser import CheckResult, LoginStateNotifier, VmissMonitor
from vmiss_notify.config import AppConfig
from vmiss_notify.stock import StockStatus


class FakeNotifier:
    def __init__(self):
        self.messages = []

    def send_text(self, content):
        self.messages.append(content)


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


class FailingStartupNotifier:
    def __init__(self):
        self.calls = 0

    def send_text(self, content):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("notify failed")


class OneShotMonitor(VmissMonitor):
    def __init__(self, config, notifier):
        super().__init__(config, notifier)
        self.run_once_called = False

    def run_once(self):
        self.run_once_called = True
        return CheckResult(StockStatus.AVAILABLE, ordered=True, message="ordered")


class LoginStateNotifierTest(unittest.TestCase):
    def test_notify_login_success_once(self):
        notifier = FakeNotifier()
        login_notifier = LoginStateNotifier(notifier)

        login_notifier.notify_success("US.LA.CN2.Pro")
        login_notifier.notify_success("US.LA.CN2.Pro")

        self.assertEqual(notifier.messages, ["VMISS 登录成功，开始监控：US.LA.CN2.Pro"])


class VmissMonitorNotificationTest(unittest.TestCase):
    def test_monitor_continues_when_startup_notification_fails(self):
        notifier = FailingStartupNotifier()
        monitor = OneShotMonitor(make_config(), notifier)

        monitor.monitor_forever()

        self.assertTrue(monitor.run_once_called)


if __name__ == "__main__":
    unittest.main()
