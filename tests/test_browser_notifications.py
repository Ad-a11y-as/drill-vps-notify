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

        self.assertEqual(notifier.messages, ["服务监控开始"])


class VmissMonitorNotificationTest(unittest.TestCase):
    def test_monitor_continues_when_startup_notification_fails(self):
        notifier = FailingStartupNotifier()
        monitor = OneShotMonitor(make_config(), notifier)

        monitor.monitor_forever()

        self.assertTrue(monitor.run_once_called)

    def test_monitor_startup_notification_does_not_expose_service_name_or_product(self):
        notifier = FakeNotifier()
        monitor = OneShotMonitor(make_config(), notifier)

        monitor.monitor_forever()

        self.assertIn("服务监控开始", notifier.messages)
        for message in notifier.messages:
            self.assertNotIn("VMISS", message)
            self.assertNotIn("US.LA.CN2.Basic", message)

    def test_available_notification_is_generic(self):
        notifier = FakeNotifier()
        monitor = VmissMonitor(make_config(), notifier)

        result = monitor._check_and_order(FakeAvailablePage())

        self.assertTrue(result.ordered)
        self.assertEqual(result.message, "服务可达")
        self.assertEqual(notifier.messages, ["服务可达"])

class FakeAvailablePage:
    def wait_for_load_state(self, state, timeout=None):
        return None

    def get_by_text(self, text, exact=False):
        return FakeProductLocator()


class FakeProductLocator:
    @property
    def first(self):
        return self

    def wait_for(self, timeout=None):
        return None

    def locator(self, selector):
        return FakeProductCard()


class FakeProductCard:
    def inner_text(self, timeout=None):
        return "US.LA.CN2.Basic\n1 Available\nOrder Now"

    def get_by_role(self, role, name=None):
        return FakeEmptyLocator()

    def get_by_text(self, text):
        return FakeOrderLocator()


class FakeEmptyLocator:
    def count(self):
        return 0


class FakeOrderLocator:
    @property
    def first(self):
        return self

    def is_visible(self, timeout=None):
        return True

    def evaluate(self, script):
        return False

    def click(self, timeout=None):
        return None


if __name__ == "__main__":
    unittest.main()
