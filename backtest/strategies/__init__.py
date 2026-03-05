"""전략 레지스트리"""

from backtest.strategies.base import Signal, Strategy
from backtest.strategies.bb_rsi_ema import BbRsiEma

STRATEGIES: dict[str, type[Strategy]] = {
    "bb_rsi_ema": BbRsiEma,
}

__all__ = ["STRATEGIES", "BbRsiEma", "Signal", "Strategy"]
