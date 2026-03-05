"""Phase 3 Step 2: engine.py run_backtest TC"""

import numpy as np
import pandas as pd
import pytest

from backtest.engine import run_backtest
from backtest.strategies.base import Signal, Strategy
from config import FeeModel


class AlwaysHold(Strategy):
    def generate_signals(self, df):
        return pd.Series(Signal.HOLD, index=df.index)

    @property
    def params(self):
        return {"name": "hold"}


class BuySellOnce(Strategy):
    """첫 날 BUY, 마지막 날 SELL"""
    def generate_signals(self, df):
        signals = pd.Series(Signal.HOLD, index=df.index)
        signals.iloc[0] = Signal.BUY
        signals.iloc[-1] = Signal.SELL
        return signals

    @property
    def params(self):
        return {"name": "buy_sell_once"}


@pytest.fixture()
def ohlcv_100():
    dates = pd.date_range("2023-01-02", periods=100, freq="B")
    rng = np.random.default_rng(42)
    close = 100 + rng.standard_normal(100).cumsum()
    return pd.DataFrame(
        {
            "open": close + rng.uniform(-0.5, 0.5, 100),
            "high": close + rng.uniform(0, 1, 100),
            "low": close - rng.uniform(0, 1, 100),
            "close": close,
            "volume": rng.integers(1_000_000, 10_000_000, 100),
        },
        index=dates,
    )


# ── TC-1: run_backtest 반환 타입 ──
def test_run_backtest_return_keys(ohlcv_100):
    result = run_backtest(ohlcv_100, AlwaysHold())
    for key in ("equity_curve", "total_trades", "final_equity", "trades", "params"):
        assert key in result


# ── TC-2: total_trades 포함 ──
def test_total_trades_type(ohlcv_100):
    result = run_backtest(ohlcv_100, AlwaysHold())
    assert isinstance(result["total_trades"], int)


# ── TC-3: equity_curve 타입 ──
def test_equity_curve_type(ohlcv_100):
    result = run_backtest(ohlcv_100, AlwaysHold())
    assert isinstance(result["equity_curve"], list)
    if result["equity_curve"]:
        assert "date" in result["equity_curve"][0]
        assert "equity" in result["equity_curve"][0]


# ── TC-4: 수수료 적용 ──
def test_fee_impact(ohlcv_100):
    r_fee = run_backtest(ohlcv_100, BuySellOnce(), fee_rate=FeeModel.STANDARD)
    r_no_fee = run_backtest(ohlcv_100, BuySellOnce(), fee_rate=0.0)
    assert r_fee["final_equity"] < r_no_fee["final_equity"]


# ── TC-5: HOLD만 시그널 ──
def test_hold_only(ohlcv_100):
    result = run_backtest(ohlcv_100, AlwaysHold())
    assert result["total_trades"] == 0
    assert result["final_equity"] == pytest.approx(2000)


# ── TC-6: BUY→SELL 1회 거래 ──
def test_buy_sell_once(ohlcv_100):
    result = run_backtest(ohlcv_100, BuySellOnce())
    assert result["total_trades"] == 2


# ── TC-7: 전략 파라미터 전달 ──
def test_params_in_result(ohlcv_100):
    result = run_backtest(ohlcv_100, BuySellOnce())
    assert result["params"] == {"name": "buy_sell_once"}


# ── TC-8: 빈 데이터 처리 ──
def test_empty_dataframe():
    df = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    result = run_backtest(df, AlwaysHold())
    assert result["total_trades"] == 0
    assert result["final_equity"] == 2000
