import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vmiss_notify.config import AppConfig
from vmiss_notify.nodriver_browser import NodriverMonitor, build_nodriver_start_options


class NodriverBrowserTest(unittest.TestCase):
    def test_build_start_options_forces_headed_shared_profile(self):
        config = make_config()

        options = build_nodriver_start_options(config)

        self.assertFalse(options["headless"])
        self.assertEqual(options["user_data_dir"], str(Path(".browser-profile")))

    def test_run_once_reuses_single_tab_and_sends_available_notification(self):
        notifier = FakeNotifier()
        browser = FakeBrowser(FakeTab("US.LA.CN2.Basic\n1 Available\nOrder Now"))
        monitor = NodriverMonitor(
            make_config(),
            notifier,
            browser_factory=lambda **kwargs: browser,
            async_sleep=no_sleep,
        )

        result = monitor.run_once()

        self.assertTrue(result.ordered)
        self.assertEqual(notifier.messages, ["服务可达"])
        self.assertEqual(browser.opened_urls, ["https://app.vmiss.com/store/us-los-angeles-cn2"])
        self.assertTrue(browser.stopped)

    def test_unavailable_result_includes_timestamp(self):
        notifier = FakeNotifier()
        browser = FakeBrowser(FakeTab("US.LA.CN2.Basic\n0 Available\nSold Out"))
        monitor = NodriverMonitor(
            make_config(),
            notifier,
            browser_factory=lambda **kwargs: browser,
            async_sleep=no_sleep,
        )

        result = monitor.run_once()

        self.assertFalse(result.ordered)
        self.assertRegex(result.message, r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} US\.LA\.CN2\.Basic 暂无库存$")
        self.assertEqual(notifier.messages, [])

    def test_monitor_startup_notification_is_generic(self):
        notifier = FakeNotifier()
        browser = FakeBrowser(FakeTab("US.LA.CN2.Basic\n1 Available\nOrder Now"))
        monitor = NodriverMonitor(
            make_config(),
            notifier,
            browser_factory=lambda **kwargs: browser,
            async_sleep=no_sleep,
        )

        monitor.monitor_forever()

        self.assertEqual(notifier.messages, ["服务监控开始", "服务可达"])
        for message in notifier.messages:
            self.assertNotIn("VMISS", message)
            self.assertNotIn("US.LA.CN2.Basic", message)

    def test_monitor_exception_notification_is_generic(self):
        notifier = FakeNotifier()
        browser = FakeBrowser(FakeTab("US.LA.CN2.Basic\n1 Available\nOrder Now"), fail_content_on_call=2)
        monitor = NodriverMonitor(
            make_config(),
            notifier,
            browser_factory=lambda **kwargs: browser,
            async_sleep=no_sleep,
        )

        monitor.monitor_forever()

        self.assertIn("服务监控异常", notifier.messages)
        self.assertIn("服务可达", notifier.messages)
        for message in notifier.messages:
            self.assertNotIn("RuntimeError", message)
            self.assertNotIn("secret backend detail", message)

    def test_cloudflare_requires_manual_confirmation(self):
        notifier = FakeNotifier()
        prompts = []
        browser = FakeBrowser(FakeTab("Verify you are human"))
        monitor = NodriverMonitor(
            make_config(),
            notifier,
            browser_factory=lambda **kwargs: browser,
            input_func=lambda prompt: prompts.append(prompt),
            async_sleep=no_sleep,
        )

        monitor.setup_login()

        self.assertEqual(notifier.messages[0], "服务需要验证重启。")
        self.assertEqual(len(prompts), 2)
        self.assertIn("手动完成验证", prompts[0])


class FakeNotifier:
    def __init__(self):
        self.messages = []

    def send_text(self, content):
        self.messages.append(content)


class FakeBrowser:
    def __init__(self, tab, fail_content_on_call=None):
        self._tab = tab
        self._tab.fail_content_on_call = fail_content_on_call
        self.opened_urls = []
        self.stopped = False

    async def get(self, url):
        self.opened_urls.append(url)
        return self._tab

    def stop(self):
        self.stopped = True


class FakeTab:
    def __init__(self, content):
        self.content = content
        self.fail_content_on_call = None
        self.content_calls = 0
        self.clicked = False
        self.brought_to_front = False

    async def get_content(self):
        self.content_calls += 1
        if self.content_calls == self.fail_content_on_call:
            self.fail_content_on_call = None
            raise RuntimeError("secret backend detail")
        return self.content

    async def find(self, text, best_match=False):
        if text == "Order Now" and "Order Now" in self.content:
            return FakeElement(self)
        return None

    async def select(self, selector, timeout=1):
        return None

    async def reload(self):
        return None

    async def bring_to_front(self):
        self.brought_to_front = True


class FakeElement:
    def __init__(self, tab):
        self._tab = tab

    async def click(self):
        self._tab.clicked = True

    async def send_keys(self, text):
        return None


async def no_sleep(seconds):
    return None


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
        message_to_users=["user1"],
        browser_channel="chrome",
        token_refresh_after_seconds=6600,
    )


if __name__ == "__main__":
    unittest.main()
