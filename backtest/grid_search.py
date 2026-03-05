"""파라미터 그리드 서치"""

import itertools
from concurrent.futures import ProcessPoolExecutor

import pandas as pd

from backtest.buyhold import compute_buyhold
from backtest.data_loader import resample_to_weekly
from backtest.engine import run_backtest
from backtest.metrics import compute_metrics
from backtest.strategies.bb_rsi_ema import BbRsiEma
from config import CAPITAL, FeeModel

DEFAULT_GRID = {
    "bb_window": [15, 20, 25, 30],
    "bb_std": [1.5, 2.0, 2.5, 3.0],
    "rsi_window": [10, 14, 21],
    "ema_window": [20, 50, 100, 200],
    "rsi_buy_threshold": [25, 30, 35, 40],
    "rsi_sell_threshold": [60, 65, 70, 75],
    "ema_filter": [True, False],
    "macd_filter": [True, False],
    "volume_filter": [True, False],
    "adx_filter": [True, False],
}


def generate_param_combos(grid: dict | None = None) -> list[dict]:
    if grid is None:
        grid = DEFAULT_GRID
    keys = list(grid.keys())
    values = list(grid.values())
    return [dict(zip(keys, combo)) for combo in itertools.product(*values)]


def run_grid_search(
    df: pd.DataFrame,
    grid: dict | None = None,
    capital: float = CAPITAL,
    fee_rate: float = FeeModel.STANDARD,
    top_n: int | None = None,
) -> list[dict]:
    combos = generate_param_combos(grid)
    bh = compute_buyhold(df, capital=capital, fee_rate=fee_rate)
    bh_return = bh["total_return"]

    results = []
    for params in combos:
        strategy = BbRsiEma(**params)
        bt = run_backtest(df, strategy, capital=capital, fee_rate=fee_rate)
        metrics = compute_metrics(bt["equity_curve"], total_trades=bt["total_trades"])
        s_return = metrics["total_return"]
        results.append({
            "params": params,
            "total_trades": metrics["total_trades"],
            "vs_buyhold_excess": s_return - bh_return,
            **metrics,
        })

    results.sort(key=lambda x: x.get("sharpe_ratio", 0), reverse=True)

    if top_n:
        results = results[:top_n]

    return results


_PERIOD_YEARS = {"1y": 1, "3y": 3, "5y": 5}
_FEE_LABELS = {FeeModel.STANDARD: "standard", FeeModel.EVENT: "event"}


def _slice_period(df: pd.DataFrame, period: str) -> pd.DataFrame:
    years = _PERIOD_YEARS.get(period)
    if years is None or df.empty:
        return df
    end = df.index[-1]
    start = end - pd.DateOffset(years=years)
    return df[df.index >= start]


def _fee_label(fee_rate: float) -> str:
    for model, label in _FEE_LABELS.items():
        if abs(float(model) - fee_rate) < 1e-9:
            return label
    return f"fee_{fee_rate}"


def _run_symbol(
    symbol: str,
    df: pd.DataFrame,
    grid: dict,
    capital: float,
    fee_rates: list[float],
    top_n: int,
    periods: list[str],
    timeframes: list[str],
) -> tuple[str, dict]:
    symbol_result = {}
    for tf in timeframes:
        tf_df = resample_to_weekly(df) if tf == "weekly" else df
        tf_result = {}
        for period in periods:
            period_df = _slice_period(tf_df, period)
            if period_df.empty:
                continue
            period_result = {}
            for fee_rate in fee_rates:
                label = _fee_label(fee_rate)
                period_result[label] = run_grid_search(
                    period_df, grid=grid, capital=capital,
                    fee_rate=fee_rate, top_n=top_n,
                )
            tf_result[period] = period_result
        symbol_result[tf] = tf_result
    return symbol, symbol_result


def run_full_grid_search(
    data: dict[str, pd.DataFrame],
    grid: dict | None = None,
    capital: float = CAPITAL,
    fee_rates: list[float] | None = None,
    top_n: int = 5,
    periods: list[str] | None = None,
    timeframes: list[str] | None = None,
    n_jobs: int | None = None,
) -> dict:
    if grid is None:
        grid = DEFAULT_GRID
    if fee_rates is None:
        fee_rates = [float(FeeModel.STANDARD), float(FeeModel.EVENT)]
    if periods is None:
        periods = ["1y", "3y", "5y"]
    if timeframes is None:
        timeframes = ["daily", "weekly"]

    results = {}

    if n_jobs and n_jobs > 1:
        with ProcessPoolExecutor(max_workers=n_jobs) as executor:
            futures = {
                executor.submit(
                    _run_symbol, sym, df, grid, capital,
                    fee_rates, top_n, periods, timeframes,
                ): sym
                for sym, df in data.items()
            }
            for future in futures:
                sym, sym_result = future.result()
                results[sym] = sym_result
    else:
        for sym, df in data.items():
            _, sym_result = _run_symbol(
                sym, df, grid, capital,
                fee_rates, top_n, periods, timeframes,
            )
            results[sym] = sym_result

    return results
