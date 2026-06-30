import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vmiss_notify.browser import prepare_manual_cloudflare_verification


class FakePage:
    def __init__(self):
        self.brought_to_front = False

    def bring_to_front(self):
        self.brought_to_front = True


class CloudflareManualVerificationTest(unittest.TestCase):
    def test_prepare_manual_verification_brings_visible_browser_to_front(self):
        page = FakePage()

        message = prepare_manual_cloudflare_verification(page, headless=False)

        self.assertTrue(page.brought_to_front)
        self.assertIn("手动点击", message)

    def test_prepare_manual_verification_rejects_headless_browser(self):
        page = FakePage()

        with self.assertRaises(RuntimeError) as exc_info:
            prepare_manual_cloudflare_verification(page, headless=True)

        self.assertFalse(page.brought_to_front)
        self.assertIn("HEADLESS=false", str(exc_info.exception))


if __name__ == "__main__":
    unittest.main()
