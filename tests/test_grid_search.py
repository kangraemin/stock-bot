"""grid_search.py TC"""

import numpy as np
import pandas as pd
import pytest

from backtest.grid_search import DEFAULT_GRID, generate_param_combos, run_grid_search

try:
    from backtest.grid_search import run_full_grid_search
except ImportError:
    run_full_grid_search = None


@pytest.fixture()
def price_df():
    dates = pd.date_range("2022-01-03", periods=200, freq="B")
    rng = np.random.default_rng(42)
    close = 100 + rng.standard_normal(200).cumsum()
    return pd.DataFrame(
        {
            "open": close,
            "high": close + 1,
            "low": close - 1,
            "close": close,
            "volume": rng.integers(1_000_000, 10_000_000, 200),
        },
        index=dates,
    )


SMALL_GRID = {
    "bb_window": [20],
    "bb_std": [2.0],
    "rsi_window": [14],
    "ema_window": [50],
}


# ── TC-1: grid_search 반환 ──
def test_grid_search_return(price_df):
    results = run_grid_search(price_df, grid=SMALL_GRID)
    assert isinstance(results, list)
    assert len(results) > 0
    assert "params" in results[0]


# ── TC-2: 결과에 total_trades ──
def test_grid_results_have_total_trades(price_df):
    results = run_grid_search(price_df, grid=SMALL_GRID)
    for r in results:
        assert "total_trades" in r


# ── TC-3: 결과에 vs_buyhold_excess ──
def test_grid_results_have_excess(price_df):
    results = run_grid_search(price_df, grid=SMALL_GRID)
    for r in results:
        assert "vs_buyhold_excess" in r


# ── TC-4: 결과 정렬 ──
def test_grid_sorted_by_sharpe(price_df):
    grid = {"bb_window": [15, 20], "bb_std": [2.0], "rsi_window": [14], "ema_window": [50]}
    results = run_grid_search(price_df, grid=grid)
    sharpes = [r["sharpe_ratio"] for r in results]
    assert sharpes == sorted(sharpes, reverse=True)


# ── TC-5: 파라미터 조합 생성 ──
def test_param_combos():
    grid = {"a": [1, 2], "b": [3, 4, 5]}
    combos = generate_param_combos(grid)
    assert len(combos) == 6


# ── TC-6: top_n 필터 ──
def test_top_n(price_df):
    grid = {"bb_window": [15, 20, 25], "bb_std": [2.0], "rsi_window": [14], "ema_window": [50]}
    results = run_grid_search(price_df, grid=grid, top_n=2)
    assert len(results) == 2
