import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vmiss_notify.browser import ORDER_TEXT_RE, bring_page_to_front


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


class FakePage:
    def __init__(self):
        self.brought_to_front = False

    def bring_to_front(self):
        self.brought_to_front = True


class BrokenPage:
    def bring_to_front(self):
        raise RuntimeError("window not available")


if __name__ == "__main__":
    unittest.main()
