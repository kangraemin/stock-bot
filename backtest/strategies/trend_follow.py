"""추세추종 전략: Dual EMA Crossover + ATR Trailing Stop

프랍 트레이더 관점:
- 미국 대형주는 추세장 → 추세추종이 맞다
- ATR 기반 트레일링 스탑 → 추세 끝날 때 자동 청산
- 필터 최소화 → 신호 빈도 확보
"""

import numpy as np
import pandas as pd
import ta

from backtest.strategies.base import Signal, Strategy


class TrendFollow(Strategy):
    def __init__(
        self,
        fast_ema: int = 10,
        slow_ema: int = 30,
        atr_window: int = 14,
        atr_multiplier: float = 2.0,
        adx_threshold: float = 20.0,
        use_adx_filter: bool = True,
    ):
        self._fast_ema = fast_ema
        self._slow_ema = slow_ema
        self._atr_window = atr_window
        self._atr_multiplier = atr_multiplier
        self._adx_threshold = adx_threshold
        self._use_adx_filter = use_adx_filter

    @property
    def params(self) -> dict:
        return {
            "fast_ema": self._fast_ema,
            "slow_ema": self._slow_ema,
            "atr_window": self._atr_window,
            "atr_multiplier": self._atr_multiplier,
            "adx_threshold": self._adx_threshold,
            "use_adx_filter": self._use_adx_filter,
        }

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        close = df["close"]
        high = df["high"]
        low = df["low"]
        signals = pd.Series(Signal.HOLD, index=df.index)

        min_periods = max(self._slow_ema, self._atr_window) + 5
        if len(df) < min_periods:
            return signals

        fast = ta.trend.EMAIndicator(close, window=self._fast_ema).ema_indicator()
        slow = ta.trend.EMAIndicator(close, window=self._slow_ema).ema_indicator()
        atr = ta.volatility.AverageTrueRange(high, low, close, window=self._atr_window).average_true_range()

        if self._use_adx_filter:
            adx = ta.trend.ADXIndicator(high, low, close, window=14).adx()
        else:
            adx = pd.Series(100.0, index=df.index)  # always pass

        # Crossover detection
        fast_vals = fast.values
        slow_vals = slow.values
        adx_vals = adx.values
        close_vals = close.values
        atr_vals = atr.values

        in_position = False
        trailing_stop = 0.0

        for i in range(1, len(df)):
            if np.isnan(fast_vals[i]) or np.isnan(slow_vals[i]) or np.isnan(atr_vals[i]):
                continue

            if not in_position:
                # BUY: fast crosses above slow + ADX filter
                crossed_up = fast_vals[i] > slow_vals[i] and fast_vals[i - 1] <= slow_vals[i - 1]
                adx_ok = adx_vals[i] > self._adx_threshold if not np.isnan(adx_vals[i]) else False

                if crossed_up and adx_ok:
                    signals.iloc[i] = Signal.BUY
                    in_position = True
                    trailing_stop = close_vals[i] - atr_vals[i] * self._atr_multiplier
            else:
                # Update trailing stop
                new_stop = close_vals[i] - atr_vals[i] * self._atr_multiplier
                if new_stop > trailing_stop:
                    trailing_stop = new_stop

                # SELL conditions:
                # 1) Trailing stop hit
                # 2) Fast crosses below slow (trend reversal)
                stop_hit = close_vals[i] < trailing_stop
                crossed_down = fast_vals[i] < slow_vals[i] and fast_vals[i - 1] >= slow_vals[i - 1]

                if stop_hit or crossed_down:
                    signals.iloc[i] = Signal.SELL
                    in_position = False

        return signals
