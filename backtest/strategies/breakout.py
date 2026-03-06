"""돈키안 채널 브레이크아웃 전략

프랍 트레이더 관점:
- 터틀 트레이딩의 핵심 전략
- N일 고점 돌파 매수, N/2일 저점 이탈 매도
- 볼륨 확인으로 거짓 돌파 필터링
- 추세장에서 큰 움직임 포착
"""

import numpy as np
import pandas as pd

from backtest.strategies.base import Signal, Strategy


class DonchianBreakout(Strategy):
    def __init__(
        self,
        entry_window: int = 20,
        exit_window: int = 10,
        volume_confirm: bool = True,
        volume_mult: float = 1.3,
    ):
        self._entry_window = entry_window
        self._exit_window = exit_window
        self._volume_confirm = volume_confirm
        self._volume_mult = volume_mult

    @property
    def params(self) -> dict:
        return {
            "entry_window": self._entry_window,
            "exit_window": self._exit_window,
            "volume_confirm": self._volume_confirm,
            "volume_mult": self._volume_mult,
        }

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        close = df["close"]
        high = df["high"]
        low = df["low"]
        volume = df["volume"].astype(float)
        signals = pd.Series(Signal.HOLD, index=df.index)

        if len(df) < self._entry_window + 2:
            return signals

        # Donchian channels
        entry_high = high.rolling(self._entry_window).max().shift(1)
        exit_low = low.rolling(self._exit_window).min().shift(1)
        vol_avg = volume.rolling(20).mean()

        close_vals = close.values
        entry_high_vals = entry_high.values
        exit_low_vals = exit_low.values
        vol_vals = volume.values
        vol_avg_vals = vol_avg.values

        in_position = False

        for i in range(self._entry_window + 1, len(df)):
            if np.isnan(entry_high_vals[i]) or np.isnan(exit_low_vals[i]):
                continue

            if not in_position:
                # BUY: close breaks above entry_window high
                breakout = close_vals[i] > entry_high_vals[i]

                if self._volume_confirm and not np.isnan(vol_avg_vals[i]):
                    vol_ok = vol_vals[i] > vol_avg_vals[i] * self._volume_mult
                else:
                    vol_ok = True

                if breakout and vol_ok:
                    signals.iloc[i] = Signal.BUY
                    in_position = True
            else:
                # SELL: close breaks below exit_window low
                if close_vals[i] < exit_low_vals[i]:
                    signals.iloc[i] = Signal.SELL
                    in_position = False

        return signals
