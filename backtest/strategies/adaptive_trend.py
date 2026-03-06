"""Adaptive Trend + Regime Filter 전략

프랍 트레이더 3인 합의:
- SMA(200) 위 = 상승 레짐 → 롱 허용
- SMA(200) 아래 = 하락 레짐 → 현금
- EMA(10)/EMA(30) 크로스로 진입/청산 타이밍
- ATR(14) 트레일링 스탑으로 리스크 관리

핵심: 상승장에선 B&H에 가깝게, 하락장에선 현금으로 MDD 축소
"""

import numpy as np
import pandas as pd
import ta

from backtest.strategies.base import Signal, Strategy


class AdaptiveTrend(Strategy):
    def __init__(
        self,
        sma_period: int = 200,
        fast_ema: int = 10,
        slow_ema: int = 30,
        atr_window: int = 14,
        atr_multiplier: float = 2.0,
    ):
        self._sma_period = sma_period
        self._fast_ema = fast_ema
        self._slow_ema = slow_ema
        self._atr_window = atr_window
        self._atr_multiplier = atr_multiplier

    @property
    def params(self) -> dict:
        return {
            "sma_period": self._sma_period,
            "fast_ema": self._fast_ema,
            "slow_ema": self._slow_ema,
            "atr_window": self._atr_window,
            "atr_multiplier": self._atr_multiplier,
        }

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        close = df["close"]
        high = df["high"]
        low = df["low"]
        signals = pd.Series(Signal.HOLD, index=df.index)

        min_periods = self._sma_period + 5
        if len(df) < min_periods:
            return signals

        sma200 = ta.trend.SMAIndicator(close, window=self._sma_period).sma_indicator()
        fast = ta.trend.EMAIndicator(close, window=self._fast_ema).ema_indicator()
        slow = ta.trend.EMAIndicator(close, window=self._slow_ema).ema_indicator()
        atr = ta.volatility.AverageTrueRange(
            high, low, close, window=self._atr_window
        ).average_true_range()

        sma_vals = sma200.values
        fast_vals = fast.values
        slow_vals = slow.values
        close_vals = close.values
        atr_vals = atr.values

        in_position = False
        trailing_stop = 0.0
        highest_since_entry = 0.0
        warmup_done = False

        for i in range(1, len(df)):
            if (
                np.isnan(sma_vals[i])
                or np.isnan(fast_vals[i])
                or np.isnan(slow_vals[i])
                or np.isnan(atr_vals[i])
            ):
                continue

            bull_regime = close_vals[i] > sma_vals[i]

            if not in_position:
                if bull_regime:
                    # 첫 유효 시점에서 이미 bull + fast>slow면 즉시 진입
                    already_above = fast_vals[i] > slow_vals[i]
                    crossed_up = (
                        fast_vals[i] > slow_vals[i]
                        and fast_vals[i - 1] <= slow_vals[i - 1]
                    )
                    enter = crossed_up or (not warmup_done and already_above)
                    if enter:
                        signals.iloc[i] = Signal.BUY
                        in_position = True
                        warmup_done = True
                        highest_since_entry = close_vals[i]
                        trailing_stop = (
                            close_vals[i] - atr_vals[i] * self._atr_multiplier
                        )
                    elif not warmup_done:
                        warmup_done = True
            else:
                # Update trailing stop
                if close_vals[i] > highest_since_entry:
                    highest_since_entry = close_vals[i]
                new_stop = close_vals[i] - atr_vals[i] * self._atr_multiplier
                if new_stop > trailing_stop:
                    trailing_stop = new_stop

                # SELL conditions (any one triggers)
                # 1) 레짐 전환: close < SMA(200)
                regime_exit = not bull_regime
                # 2) EMA 데드크로스
                crossed_down = (
                    fast_vals[i] < slow_vals[i]
                    and fast_vals[i - 1] >= slow_vals[i - 1]
                )
                # 3) 트레일링 스탑
                stop_hit = close_vals[i] < trailing_stop

                if regime_exit or crossed_down or stop_hit:
                    signals.iloc[i] = Signal.SELL
                    in_position = False

        return signals
