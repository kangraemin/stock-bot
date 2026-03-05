"""전역 설정: 심볼, 수수료, 프리셋 등"""

from enum import Enum


# ── 심볼 ──
SYMBOLS_BASE = ["SPY", "QQQ", "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "TSLA"]

SYMBOLS_3X = ["TQQQ", "SPXL", "SOXL", "UPRO", "TECL"]

LEVERAGE_MAP = {
    "TQQQ": "QQQ",
    "SPXL": "SPY",
    "SOXL": "QQQ",
    "UPRO": "SPY",
    "TECL": "QQQ",
}

# ── 수수료 / 슬리피지 ──
class FeeModel(float, Enum):
    STANDARD = 0.0025
    EVENT = 0.0009


SLIPPAGE = 0.001

# ── 자본금 ──
CAPITAL = 2000

# ── 포트폴리오 프리셋 (symbol -> weight) ──
PRESET_MIXED = {
    "TQQQ": 0.30,
    "SPXL": 0.20,
    "SPY": 0.20,
    "MSFT": 0.15,
    "AAPL": 0.15,
}

PRESET_ALL_3X = {s: 0.20 for s in SYMBOLS_3X}

PRESET_GROWTH = {s: 0.20 for s in ["TQQQ", "TECL", "SOXL", "NVDA", "TSLA"]}

PRESET_SAFE = {s: 0.25 for s in ["SPY", "MSFT", "GOOGL", "AAPL"]}
