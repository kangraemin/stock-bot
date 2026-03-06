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


# ── Phase 2 Step 2: Grid Search 확장 ──

SMALL_FULL_GRID = {
    "bb_window": [20, 25],
    "bb_std": [2.0, 2.5],
    "rsi_window": [14, 21],
    "ema_window": [50, 100],
    "rsi_buy_threshold": [30, 35],
    "rsi_sell_threshold": [65, 70],
    "ema_filter": [False, True],
    "macd_filter": [False, True],
    "volume_filter": [False, True],
    "adx_filter": [False, True],
}


# ── TC-7: DEFAULT_GRID 10개 파라미터 키 ──
def test_default_grid_has_10_params():
    assert len(DEFAULT_GRID) == 10


# ── TC-8: DEFAULT_GRID 조합 수 49,152 ──
def test_default_grid_combo_count_49152():
    combos = generate_param_combos()
    assert len(combos) == 49_152


# ── TC-9: generate_param_combos에 새 파라미터 포함 ──
def test_param_combos_include_new_params():
    combos = generate_param_combos()
    new_params = {"rsi_buy_threshold", "rsi_sell_threshold", "ema_filter",
                  "macd_filter", "volume_filter", "adx_filter"}
    for key in new_params:
        assert key in combos[0], f"Missing param: {key}"


# ── TC-10: run_full_grid_search 반환 구조 ──
def test_full_grid_search_return_structure(price_df):
    assert run_full_grid_search is not None, "run_full_grid_search not implemented"
    data = {"SPY": price_df}
    result = run_full_grid_search(data, grid=SMALL_FULL_GRID, top_n=2)
    assert isinstance(result, dict)
    assert "SPY" in result
    spy = result["SPY"]
    assert isinstance(spy, dict)
    first_tf = next(iter(spy.values()))
    assert isinstance(first_tf, dict)
    first_period = next(iter(first_tf.values()))
    assert isinstance(first_period, dict)
    first_fee = next(iter(first_period.values()))
    assert isinstance(first_fee, list)


# ── TC-11: run_full_grid_search 다중 심볼 ──
def test_full_grid_search_multi_symbol(price_df):
    assert run_full_grid_search is not None, "run_full_grid_search not implemented"
    data = {"SPY": price_df, "QQQ": price_df}
    result = run_full_grid_search(data, grid=SMALL_FULL_GRID, top_n=2)
    assert "SPY" in result
    assert "QQQ" in result


# ── TC-12: run_full_grid_search top_n 제한 ──
def test_full_grid_search_top_n(price_df):
    assert run_full_grid_search is not None, "run_full_grid_search not implemented"
    data = {"SPY": price_df}
    result = run_full_grid_search(data, grid=SMALL_FULL_GRID, top_n=2)
    for symbol, timeframes in result.items():
        for tf, periods in timeframes.items():
            for period, fees in periods.items():
                for fee_label, results_list in fees.items():
                    assert len(results_list) <= 2


# ── TC-13: run_full_grid_search fee_rates ──
def test_full_grid_search_fee_rates(price_df):
    assert run_full_grid_search is not None, "run_full_grid_search not implemented"
    data = {"SPY": price_df}
    result = run_full_grid_search(
        data, grid=SMALL_FULL_GRID, top_n=2,
        fee_rates=[0.0025, 0.0009],
    )
    spy = result["SPY"]
    first_tf = next(iter(spy.values()))
    first_period = next(iter(first_tf.values()))
    assert len(first_period) == 2  # two fee rate keys


# ── TC-14: run_full_grid_search timeframes (daily/weekly) ──
def test_full_grid_search_timeframes(price_df):
    assert run_full_grid_search is not None, "run_full_grid_search not implemented"
    data = {"SPY": price_df}
    result = run_full_grid_search(data, grid=SMALL_FULL_GRID, top_n=2)
    spy = result["SPY"]
    assert "daily" in spy
    assert "weekly" in spy


# ── hourly 지원 TC ──


@pytest.fixture()
def hourly_df():
    """시간봉 데이터 (약 130개 = 20 영업일 x 6.5h)"""
    dates = pd.date_range("2024-01-02 09:30", periods=130, freq="h")
    rng = np.random.default_rng(42)
    close = 100 + rng.standard_normal(130).cumsum()
    return pd.DataFrame(
        {
            "open": close,
            "high": close + 1,
            "low": close - 1,
            "close": close,
            "volume": rng.integers(1_000_000, 10_000_000, 130),
        },
        index=dates,
    )


def test_run_grid_search_periods_per_year_param():
    """run_grid_search에 periods_per_year 파라미터 존재"""
    import inspect
    sig = inspect.signature(run_grid_search)
    assert "periods_per_year" in sig.parameters


def test_full_grid_search_hourly_data_param():
    """run_full_grid_search에 hourly_data 파라미터 존재"""
    import inspect
    assert run_full_grid_search is not None
    sig = inspect.signature(run_full_grid_search)
    assert "hourly_data" in sig.parameters


def test_full_grid_search_hourly_results(price_df, hourly_df):
    """timeframes=['hourly'] + hourly_data 시 hourly 결과"""
    assert run_full_grid_search is not None
    data = {"SPY": price_df}
    hourly_data = {"SPY": hourly_df}
    result = run_full_grid_search(
        data, grid=SMALL_FULL_GRID, top_n=2,
        timeframes=["hourly"], hourly_data=hourly_data,
    )
    assert "hourly" in result["SPY"]


def test_full_grid_search_hourly_skip_no_data(price_df):
    """hourly_data 없이 timeframes에 hourly → hourly 스킵"""
    assert run_full_grid_search is not None
    data = {"SPY": price_df}
    result = run_full_grid_search(
        data, grid=SMALL_FULL_GRID, top_n=2,
        timeframes=["hourly"],
    )
    spy = result["SPY"]
    assert "hourly" not in spy


def test_full_grid_search_mixed_timeframes(price_df, hourly_df):
    """daily + hourly 혼합"""
    assert run_full_grid_search is not None
    data = {"SPY": price_df}
    hourly_data = {"SPY": hourly_df}
    result = run_full_grid_search(
        data, grid=SMALL_FULL_GRID, top_n=2,
        timeframes=["daily", "hourly"], hourly_data=hourly_data,
    )
    spy = result["SPY"]
    assert "daily" in spy
    assert "hourly" in spy
