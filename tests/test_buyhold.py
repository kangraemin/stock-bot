"""Phase 4 Step 2: buyhold.py TC"""

import numpy as np
import pandas as pd
import pytest

from backtest.buyhold import compare_by_period, compare_vs_buyhold, compute_buyhold
from config import FeeModel


@pytest.fixture()
def price_df():
    dates = pd.date_range("2020-01-02", periods=500, freq="B")
    rng = np.random.default_rng(42)
    close = 100 + rng.standard_normal(500).cumsum()
    return pd.DataFrame(
        {
            "open": close,
            "high": close + 1,
            "low": close - 1,
            "close": close,
            "volume": rng.integers(1_000_000, 10_000_000, 500),
        },
        index=dates,
    )


# ── TC-1: compute_buyhold 반환 ──
def test_compute_buyhold_return(price_df):
    r = compute_buyhold(price_df)
    assert "final_equity" in r
    assert "total_return" in r


# ── TC-2: compute_buyhold 수수료 ──
def test_compute_buyhold_fee(price_df):
    r_fee = compute_buyhold(price_df, fee_rate=FeeModel.STANDARD)
    r_no = compute_buyhold(price_df, fee_rate=0.0)
    assert r_fee["final_equity"] < r_no["final_equity"]


# ── TC-3: compare_vs_buyhold ──
def test_compare_vs_buyhold(price_df):
    bh = compute_buyhold(price_df)
    strategy = {"total_return": 0.5, "final_equity": 3000}
    r = compare_vs_buyhold(strategy, bh)
    assert "strategy_return" in r
    assert "buyhold_return" in r
    assert "excess_return" in r


# ── TC-4: excess_return 계산 ──
def test_excess_return():
    s = {"total_return": 0.3}
    b = {"total_return": 0.2}
    r = compare_vs_buyhold(s, b)
    assert r["excess_return"] == pytest.approx(0.1)


# ── TC-5: compare_by_period ──
def test_compare_by_period(price_df):
    r = compare_by_period(price_df, {}, periods=["1y"])
    assert isinstance(r, list)
    assert len(r) >= 1
    assert r[0]["period"] == "1y"


# ── TC-6: 빈 데이터 처리 ──
def test_compute_buyhold_empty():
    df = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    r = compute_buyhold(df)
    assert r["total_return"] == 0.0
