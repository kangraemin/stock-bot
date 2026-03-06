"""모멘텀 전략: Rate of Change + 이동평균 필터

프랍 트레이더 관점:
- "이기고 있는 놈에 올라타라" (momentum factor)
- ROC 양수 + 가격이 MA 위 = 상승 모멘텀 확인
- ROC 음수 전환 or MA 하향 돌파 = 청산
- 빈번한 진입/청산으로 충분한 표본 확보
"""

import numpy as np
import pandas as pd
import ta

from backtest.strategies.base import Signal, Strategy


class MomentumROC(Strategy):
    def __init__(
        self,
        roc_window: int = 20,
        ma_window: int = 50,
        roc_threshold: float = 0.0,
        exit_roc_threshold: float = -2.0,
    ):
        self._roc_window = roc_window
        self._ma_window = ma_window
        self._roc_threshold = roc_threshold
        self._exit_roc_threshold = exit_roc_threshold

    @property
    def params(self) -> dict:
        return {
            "roc_window": self._roc_window,
            "ma_window": self._ma_window,
            "roc_threshold": self._roc_threshold,
            "exit_roc_threshold": self._exit_roc_threshold,
        }

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        close = df["close"]
        signals = pd.Series(Signal.HOLD, index=df.index)

        min_periods = max(self._roc_window, self._ma_window) + 5
        if len(df) < min_periods:
            return signals

        roc = ta.momentum.ROCIndicator(close, window=self._roc_window).roc()
        ma = close.rolling(self._ma_window).mean()

        roc_vals = roc.values
        ma_vals = ma.values
        close_vals = close.values

        in_position = False

        for i in range(min_periods, len(df)):
            if np.isnan(roc_vals[i]) or np.isnan(ma_vals[i]):
                continue

            if not in_position:
                # BUY: ROC > threshold AND price > MA (upward momentum confirmed)
                if roc_vals[i] > self._roc_threshold and close_vals[i] > ma_vals[i]:
                    # Additional: ROC was negative recently (fresh momentum)
                    if i >= 3 and any(roc_vals[i - j] < 0 for j in range(1, min(4, i))):
                        signals.iloc[i] = Signal.BUY
                        in_position = True
            else:
                # SELL: ROC drops below exit threshold OR price below MA
                roc_exit = roc_vals[i] < self._exit_roc_threshold
                ma_exit = close_vals[i] < ma_vals[i]

                if roc_exit or ma_exit:
                    signals.iloc[i] = Signal.SELL
                    in_position = False

        return signals
