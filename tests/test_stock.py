import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vmiss_notify.stock import StockStatus, assess_stock


class StockTest(unittest.TestCase):
    def test_assess_stock_marks_english_zero_available_as_out_of_stock(self):
        status = assess_stock("US.LA.CN2.Basic\n$10.00 CAD\n0 Available", button_enabled=True)

        self.assertEqual(status, StockStatus.OUT_OF_STOCK)


    def test_assess_stock_marks_chinese_zero_available_as_out_of_stock(self):
        status = assess_stock("US.LA.CN2.Basic\n立即订购\n0 可用", button_enabled=True)

        self.assertEqual(status, StockStatus.OUT_OF_STOCK)


    def test_assess_stock_marks_disabled_button_as_out_of_stock(self):
        status = assess_stock("US.LA.CN2.Basic\n立即订购\n5 可用", button_enabled=False)

        self.assertEqual(status, StockStatus.OUT_OF_STOCK)


    def test_assess_stock_marks_enabled_non_zero_card_as_available(self):
        status = assess_stock("US.LA.CN2.Basic\n立即订购\n3 Available", button_enabled=True)

        self.assertEqual(status, StockStatus.AVAILABLE)


    def test_assess_stock_returns_unknown_when_card_text_is_empty(self):
        status = assess_stock("", button_enabled=True)

        self.assertEqual(status, StockStatus.UNKNOWN)


if __name__ == "__main__":
    unittest.main()
