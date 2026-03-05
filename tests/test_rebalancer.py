"""Phase 3 Step 3: Portfolio backtest + Rebalancer TC"""

import numpy as np
import pandas as pd
import pytest

from backtest.engine import run_portfolio_backtest
from backtest.rebalancer import (
    compute_target_weights_equal,
    needs_rebalance,
    should_rebalance_on_date,
)
from backtest.strategies.base import Signal, Strategy


class AlwaysHold(Strategy):
    def generate_signals(self, df):
        return pd.Series(Signal.HOLD, index=df.index)

    @property
    def params(self):
        return {"name": "hold"}


@pytest.fixture()
def multi_data():
    """2개 심볼 200일 데이터"""
    dates = pd.date_range("2023-01-02", periods=200, freq="B")
    rng = np.random.default_rng(42)
    result = {}
    for sym in ("SPY", "QQQ"):
        close = 100 + rng.standard_normal(200).cumsum()
        result[sym] = pd.DataFrame(
            {
                "open": close + rng.uniform(-0.5, 0.5, 200),
                "high": close + rng.uniform(0, 1, 200),
                "low": close - rng.uniform(0, 1, 200),
                "close": close,
                "volume": rng.integers(1_000_000, 10_000_000, 200),
            },
            index=dates,
        )
    return result


# ── TC-1: run_portfolio_backtest 반환 타입 ──
def test_portfolio_backtest_return_keys(multi_data):
    result = run_portfolio_backtest(multi_data, AlwaysHold())
    for key in ("equity_curve", "total_trades", "final_equity"):
        assert key in result


# ── TC-2: 멀티 심볼 처리 ──
def test_portfolio_multi_symbol(multi_data):
    result = run_portfolio_backtest(multi_data, AlwaysHold())
    assert result["final_equity"] > 0


# ── TC-3: rebalancer equal 모드 ──
def test_equal_weights():
    w = compute_target_weights_equal(["SPY", "QQQ", "AAPL"])
    assert len(w) == 3
    assert all(abs(v - 1/3) < 1e-9 for v in w.values())


# ── TC-4: rebalancer custom 모드 ──
def test_custom_weights(multi_data):
    weights = {"SPY": 0.6, "QQQ": 0.4}
    result = run_portfolio_backtest(multi_data, AlwaysHold(), weights=weights)
    assert result["final_equity"] > 0


# ── TC-5: 리밸런싱 임계값 2%p ──
def test_rebalance_threshold():
    current = {"SPY": 0.50, "QQQ": 0.50}
    target = {"SPY": 0.51, "QQQ": 0.49}
    assert needs_rebalance(current, target) is False  # < 2%p

    current2 = {"SPY": 0.55, "QQQ": 0.45}
    target2 = {"SPY": 0.50, "QQQ": 0.50}
    assert needs_rebalance(current2, target2) is True  # >= 2%p


# ── TC-6: 리밸런싱 거래 횟수 ──
def test_rebalance_increases_trades(multi_data):
    result = run_portfolio_backtest(multi_data, AlwaysHold(), rebalance_freq="monthly")
    # 초기 매수 (2) + 리밸런싱 거래들
    assert result["total_trades"] >= 2


# ── TC-7: monthly 리밸런싱 ──
def test_monthly_rebalance_check():
    date_start = pd.Timestamp("2023-01-02")  # 월초
    date_mid = pd.Timestamp("2023-01-15")  # 중순
    assert should_rebalance_on_date(date_start, "monthly") is True
    assert should_rebalance_on_date(date_mid, "monthly") is False


# ── TC-8: 포트폴리오 결과에 total_trades ──
def test_portfolio_result_has_total_trades(multi_data):
    result = run_portfolio_backtest(multi_data, AlwaysHold())
    assert "total_trades" in result
    assert isinstance(result["total_trades"], int)
