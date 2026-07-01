import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vmiss_notify.config import AppConfig
from vmiss_notify.seleniumbase_bridge import (
    build_seleniumbase_driver_options,
    run_seleniumbase_manual_verification,
)


class SeleniumBaseBridgeTest(unittest.TestCase):
    def test_build_options_uses_visible_chrome_and_shared_profile(self):
        config = make_config(browser_channel="chrome")

        options = build_seleniumbase_driver_options(config)

        self.assertEqual(options["browser"], "chrome")
        self.assertFalse(options["headless"])
        self.assertFalse(options["uc"])
        self.assertEqual(options["user_data_dir"], str(Path(".browser-profile")))

    def test_build_options_maps_msedge_channel_to_edge_browser(self):
        config = make_config(browser_channel="msedge")

        options = build_seleniumbase_driver_options(config)

        self.assertEqual(options["browser"], "edge")

    def test_manual_verification_opens_store_waits_and_closes_browser(self):
        config = make_config(browser_channel="chrome")
        driver = FakeDriver()
        prompts = []

        run_seleniumbase_manual_verification(
            config,
            driver_factory=lambda **kwargs: driver,
            input_func=lambda prompt: prompts.append(prompt),
        )

        self.assertEqual(driver.visited_urls, [config.store_url])
        self.assertTrue(driver.quit_called)
        self.assertEqual(len(prompts), 1)
        self.assertIn("SeleniumBase", prompts[0])


class FakeDriver:
    def __init__(self):
        self.visited_urls = []
        self.quit_called = False

    def get(self, url):
        self.visited_urls.append(url)

    def quit(self):
        self.quit_called = True


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
        message_to_users=["user1"],
        browser_channel=browser_channel,
        token_refresh_after_seconds=6600,
    )


if __name__ == "__main__":
    unittest.main()
