import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vmiss_notify.browser import ORDER_TEXT_RE, build_launch_options, bring_page_to_front
from vmiss_notify.config import AppConfig


class BrowserRulesTest(unittest.TestCase):
    def test_order_text_matches_english_and_chinese_labels(self):
        labels = ["Order Now", "order now", "立即订购", "立即订閱", "立即订阅"]

        for label in labels:
            with self.subTest(label=label):
                self.assertRegex(label, ORDER_TEXT_RE)

    def test_bring_page_to_front_calls_playwright_page_when_available(self):
        page = FakePage()

        bring_page_to_front(page)

        self.assertTrue(page.brought_to_front)

    def test_bring_page_to_front_ignores_failures(self):
        bring_page_to_front(BrokenPage())

    def test_build_launch_options_includes_browser_channel_when_configured(self):
        config = make_config(browser_channel="chrome")

        options = build_launch_options(config)

        self.assertEqual(options["channel"], "chrome")

    def test_build_launch_options_omits_browser_channel_by_default(self):
        config = make_config(browser_channel=None)

        options = build_launch_options(config)

        self.assertNotIn("channel", options)


class FakePage:
    def __init__(self):
        self.brought_to_front = False

    def bring_to_front(self):
        self.brought_to_front = True


class BrokenPage:
    def bring_to_front(self):
        raise RuntimeError("window not available")


def make_config(browser_channel):
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
        browser_channel=browser_channel,
        token_refresh_after_seconds=6600,
    )


if __name__ == "__main__":
    unittest.main()
