"""BB + RSI + EMA 평균회귀 전략"""

import pandas as pd
import ta

from backtest.strategies.base import Signal, Strategy


class BbRsiEma(Strategy):
    def __init__(
        self,
        bb_window: int = 20,
        bb_std: float = 2.0,
        rsi_window: int = 14,
        ema_window: int = 50,
    ):
        self._bb_window = bb_window
        self._bb_std = bb_std
        self._rsi_window = rsi_window
        self._ema_window = ema_window

    @property
    def params(self) -> dict:
        return {
            "bb_window": self._bb_window,
            "bb_std": self._bb_std,
            "rsi_window": self._rsi_window,
            "ema_window": self._ema_window,
        }

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        close = df["close"]
        signals = pd.Series(Signal.HOLD, index=df.index)

        min_periods = max(self._bb_window, self._rsi_window, self._ema_window)
        if len(df) < min_periods:
            return signals

        bb = ta.volatility.BollingerBands(
            close, window=self._bb_window, window_dev=self._bb_std
        )
        bb_lower = bb.bollinger_lband()
        bb_upper = bb.bollinger_hband()

        rsi = ta.momentum.RSIIndicator(close, window=self._rsi_window).rsi()
        ema = ta.trend.EMAIndicator(close, window=self._ema_window).ema_indicator()

        # BUY: close < BB하한 AND RSI < 35
        buy_mask = (close < bb_lower) & (rsi < 35)
        # SELL: close > BB상한 AND RSI > 65
        sell_mask = (close > bb_upper) & (rsi > 65)

        signals[buy_mask] = Signal.BUY
        signals[sell_mask] = Signal.SELL

        return signals
