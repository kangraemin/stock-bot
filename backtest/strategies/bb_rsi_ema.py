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
        rsi_buy_threshold: float = 35,
        rsi_sell_threshold: float = 65,
        ema_filter: bool = False,
        macd_filter: bool = False,
        volume_filter: bool = False,
        adx_filter: bool = False,
    ):
        self._bb_window = bb_window
        self._bb_std = bb_std
        self._rsi_window = rsi_window
        self._ema_window = ema_window
        self._rsi_buy_threshold = rsi_buy_threshold
        self._rsi_sell_threshold = rsi_sell_threshold
        self._ema_filter = ema_filter
        self._macd_filter = macd_filter
        self._volume_filter = volume_filter
        self._adx_filter = adx_filter

    @property
    def params(self) -> dict:
        return {
            "bb_window": self._bb_window,
            "bb_std": self._bb_std,
            "rsi_window": self._rsi_window,
            "ema_window": self._ema_window,
            "rsi_buy_threshold": self._rsi_buy_threshold,
            "rsi_sell_threshold": self._rsi_sell_threshold,
            "ema_filter": self._ema_filter,
            "macd_filter": self._macd_filter,
            "volume_filter": self._volume_filter,
            "adx_filter": self._adx_filter,
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

        # BUY: close < BB하한 AND RSI < threshold
        buy_mask = (close < bb_lower) & (rsi < self._rsi_buy_threshold)

        # Apply optional filters (AND conditions on BUY)
        if self._ema_filter:
            buy_mask = buy_mask & (close > ema)
        if self._macd_filter:
            macd_diff = ta.trend.MACD(close).macd_diff()
            buy_mask = buy_mask & (macd_diff > 0)
        if self._volume_filter:
            volume = df["volume"].astype(float)
            vol_avg = volume.rolling(20).mean() * 1.5
            buy_mask = buy_mask & (volume > vol_avg)
        if self._adx_filter:
            adx = ta.trend.ADXIndicator(df["high"], df["low"], close).adx()
            buy_mask = buy_mask & (adx < 25)

        # SELL: close > BB상한 AND RSI > threshold
        sell_mask = (close > bb_upper) & (rsi > self._rsi_sell_threshold)

        signals[buy_mask] = Signal.BUY
        signals[sell_mask] = Signal.SELL

        return signals

    def generate_signals_with_reasons(self, df: pd.DataFrame):
        close = df["close"]
        signals = pd.Series(Signal.HOLD, index=df.index)
        reasons = pd.Series("", index=df.index)

        min_periods = max(self._bb_window, self._rsi_window, self._ema_window)
        if len(df) < min_periods:
            return signals, reasons

        bb = ta.volatility.BollingerBands(
            close, window=self._bb_window, window_dev=self._bb_std
        )
        bb_lower = bb.bollinger_lband()
        bb_upper = bb.bollinger_hband()

        rsi = ta.momentum.RSIIndicator(close, window=self._rsi_window).rsi()
        ema = ta.trend.EMAIndicator(close, window=self._ema_window).ema_indicator()

        # BUY conditions
        buy_mask = (close < bb_lower) & (rsi < self._rsi_buy_threshold)

        if self._ema_filter:
            ema_ok = close > ema
            buy_mask = buy_mask & ema_ok
        if self._macd_filter:
            macd_diff = ta.trend.MACD(close).macd_diff()
            macd_ok = macd_diff > 0
            buy_mask = buy_mask & macd_ok
        if self._volume_filter:
            volume = df["volume"].astype(float)
            vol_avg = volume.rolling(20).mean() * 1.5
            vol_ok = volume > vol_avg
            buy_mask = buy_mask & vol_ok
        if self._adx_filter:
            adx = ta.trend.ADXIndicator(df["high"], df["low"], close).adx()
            adx_ok = adx < 25
            buy_mask = buy_mask & adx_ok

        sell_mask = (close > bb_upper) & (rsi > self._rsi_sell_threshold)

        signals[buy_mask] = Signal.BUY
        signals[sell_mask] = Signal.SELL

        # Build reason strings
        for idx in df.index[buy_mask]:
            parts = [
                f"Close({close[idx]:.1f}) < BB_lower({bb_lower[idx]:.1f})",
                f"RSI({rsi[idx]:.1f}) < {self._rsi_buy_threshold}",
            ]
            if self._ema_filter:
                parts.append("EMA OK")
            if self._macd_filter:
                parts.append("MACD OK")
            if self._volume_filter:
                parts.append("Volume OK")
            if self._adx_filter:
                parts.append("ADX OK")
            reasons[idx] = ", ".join(parts)

        for idx in df.index[sell_mask]:
            parts = [
                f"Close({close[idx]:.1f}) > BB_upper({bb_upper[idx]:.1f})",
                f"RSI({rsi[idx]:.1f}) > {self._rsi_sell_threshold}",
            ]
            reasons[idx] = ", ".join(parts)

        return signals, reasons
