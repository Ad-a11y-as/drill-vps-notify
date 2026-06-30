from __future__ import annotations

from enum import Enum


class StockStatus(str, Enum):
    AVAILABLE = "available"
    OUT_OF_STOCK = "out_of_stock"
    UNKNOWN = "unknown"


def assess_stock(card_text: str, button_enabled: bool) -> StockStatus:
    normalized = " ".join(card_text.split()).lower()
    if not normalized:
        return StockStatus.UNKNOWN
    if not button_enabled:
        return StockStatus.OUT_OF_STOCK
    if "0 available" in normalized or "0 可用" in normalized:
        return StockStatus.OUT_OF_STOCK
    return StockStatus.AVAILABLE
