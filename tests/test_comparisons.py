"""Phase 4 Step 4: comparisons.py TC"""

import numpy as np
import pandas as pd
import pytest

from backtest.comparisons import run_preset_comparison, run_single_vs_portfolio
from backtest.strategies.base import Signal, Strategy


class AlwaysHold(Strategy):
    def generate_signals(self, df):
        return pd.Series(Signal.HOLD, index=df.index)

    @property
    def params(self):
        return {"name": "hold"}


@pytest.fixture()
def multi_data():
    dates = pd.date_range("2022-01-03", periods=200, freq="B")
    rng = np.random.default_rng(42)
    result = {}
    for sym in ("SPY", "QQQ", "AAPL"):
        close = 100 + rng.standard_normal(200).cumsum()
        result[sym] = pd.DataFrame(
            {
                "open": close,
                "high": close + 1,
                "low": close - 1,
                "close": close,
                "volume": rng.integers(1_000_000, 10_000_000, 200),
            },
            index=dates,
        )
    return result


# ── TC-1: run_single_vs_portfolio 반환 ──
def test_single_vs_portfolio_return(multi_data):
    weights = {"SPY": 0.5, "QQQ": 0.3, "AAPL": 0.2}
    r = run_single_vs_portfolio(multi_data, AlwaysHold(), weights)
    assert "single_results" in r
    assert "portfolio_result" in r


# ── TC-2: run_preset_comparison 반환 ──
def test_preset_comparison_return(multi_data):
    presets = {"test": {"SPY": 0.5, "QQQ": 0.5}}
    r = run_preset_comparison(multi_data, AlwaysHold(), presets=presets)
    assert "test" in r


# ── TC-3: 비교 지표 포함 ──
def test_comparison_metrics(multi_data):
    presets = {"test": {"SPY": 0.5, "QQQ": 0.5}}
    r = run_preset_comparison(multi_data, AlwaysHold(), presets=presets)
    m = r["test"]
    for key in ("total_return", "max_drawdown", "sharpe_ratio", "total_trades"):
        assert key in m


# ── TC-4: PRESETS 접근 ──
def test_presets_from_config():
    from backtest.comparisons import PRESETS

    assert "growth" in PRESETS
    assert "safe" in PRESETS
    assert "mixed" in PRESETS


# ── TC-5: 빈 프리셋 처리 ──
def test_empty_presets(multi_data):
    r = run_preset_comparison(multi_data, AlwaysHold(), presets={})
    assert r == {}


# ── TC-6: excess_return 포함 ──
def test_excess_return_in_preset(multi_data):
    presets = {"test": {"SPY": 0.5, "QQQ": 0.5}}
    r = run_preset_comparison(multi_data, AlwaysHold(), presets=presets)
    assert "excess_return" in r["test"]
