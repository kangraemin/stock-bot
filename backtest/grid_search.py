"""파라미터 그리드 서치"""

import itertools
import json
import os
import sys
import threading
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from multiprocessing import Manager

import pandas as pd

from backtest.buyhold import compute_buyhold
from backtest.data_loader import resample_to_weekly
from backtest.engine import run_backtest_fast
from backtest.metrics import compute_metrics_fast
from backtest.strategies.bb_rsi_ema import BbRsiEma
from config import CAPITAL, FeeModel


def _print_progress(current: int, total: int, label: str = "") -> None:
    """Write a single-line progress update to stderr."""
    pct = current / total * 100 if total else 0
    bar_len = 30
    filled = int(bar_len * current // total) if total else 0
    bar = "\u2588" * filled + "\u2591" * (bar_len - filled)
    msg = f"\r[{bar}] {pct:5.1f}% ({current}/{total}) {label}"
    sys.stderr.write(msg)
    if current >= total:
        sys.stderr.write("\n")
    sys.stderr.flush()

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
    progress: bool = False,
    periods_per_year: int = 252,
) -> list[dict]:
    combos = generate_param_combos(grid)
    total = len(combos)
    bh = compute_buyhold(df, capital=capital, fee_rate=fee_rate)
    bh_return = bh["total_return"]

    results = []
    for i, params in enumerate(combos, 1):
        strategy = BbRsiEma(**params)
        bt = run_backtest_fast(df, strategy, capital=capital, fee_rate=fee_rate)
        metrics = compute_metrics_fast(bt["equity_curve_np"], bt["dates"], total_trades=bt["total_trades"], periods_per_year=periods_per_year)
        s_return = metrics["total_return"]
        results.append({
            "params": params,
            "total_trades": metrics["total_trades"],
            "vs_buyhold_excess": s_return - bh_return,
            **metrics,
        })
        if progress and i % 100 == 0:
            param_summary = ", ".join(f"{k}={v}" for k, v in params.items())
            _print_progress(i, total, param_summary)

    if progress:
        _print_progress(total, total, "grid search done")

    results.sort(key=lambda x: x.get("sharpe_ratio", 0), reverse=True)

    if top_n:
        results = results[:top_n]

    return results


_PERIOD_YEARS = {"1y": 1, "3y": 3, "5y": 5, "10y": 10, "20y": 20}
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
    progress: bool = False,
    progress_queue=None,
    cache_dir: str | None = None,
    hourly_df: pd.DataFrame | None = None,
) -> tuple[str, dict]:
    # Count total sub-tasks for this symbol
    sub_tasks = []
    for tf in timeframes:
        if tf == "weekly":
            tf_df = resample_to_weekly(df)
        elif tf == "hourly":
            if hourly_df is None:
                continue
            tf_df = hourly_df
        else:
            tf_df = df
        for period in periods:
            period_df = _slice_period(tf_df, period)
            if period_df.empty:
                continue
            for fee_rate in fee_rates:
                sub_tasks.append((tf, period, fee_rate, tf_df, period_df))

    total_subs = len(sub_tasks)
    symbol_result = {}

    for idx, (tf, period, fee_rate, tf_df, period_df) in enumerate(sub_tasks):
        label = _fee_label(fee_rate)
        if progress and not progress_queue:
            sys.stderr.write(f"\r  {symbol} | {tf} | {period} | {label}...")
            sys.stderr.flush()
        if progress_queue:
            progress_queue.put((symbol, tf, period, label, idx, total_subs))

        # Check cache
        cached = None
        if cache_dir:
            cached = _load_cache(cache_dir, symbol, tf, period, label)

        if cached is not None:
            result = cached
        else:
            ppy = 1638 if tf == "hourly" else 252
            result = run_grid_search(
                period_df, grid=grid, capital=capital,
                fee_rate=fee_rate, top_n=top_n,
                periods_per_year=ppy,
            )
            if cache_dir:
                _save_cache(cache_dir, symbol, tf, period, label, result)

        if tf not in symbol_result:
            symbol_result[tf] = {}
        if period not in symbol_result[tf]:
            symbol_result[tf][period] = {}
        symbol_result[tf][period][label] = result

    if progress_queue:
        progress_queue.put((symbol, "DONE", "", "", total_subs, total_subs))

    return symbol, symbol_result


def _cache_key(sym: str, tf: str, period: str, fee_label: str) -> str:
    return f"{sym}_{tf}_{period}_{fee_label}.json"


def _save_cache(cache_dir: str, sym: str, tf: str, period: str, fee_label: str, result: list) -> None:
    path = os.path.join(cache_dir, _cache_key(sym, tf, period, fee_label))
    with open(path, "w") as f:
        json.dump(result, f)


def _load_cache(cache_dir: str, sym: str, tf: str, period: str, fee_label: str) -> list | None:
    path = os.path.join(cache_dir, _cache_key(sym, tf, period, fee_label))
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return None


def run_full_grid_search(
    data: dict[str, pd.DataFrame],
    grid: dict | None = None,
    capital: float = CAPITAL,
    fee_rates: list[float] | None = None,
    top_n: int = 5,
    periods: list[str] | None = None,
    timeframes: list[str] | None = None,
    n_jobs: int | None = None,
    progress: bool = False,
    cache_dir: str | None = None,
    hourly_data: dict[str, pd.DataFrame] | None = None,
) -> dict:
    if grid is None:
        grid = DEFAULT_GRID
    if fee_rates is None:
        fee_rates = [float(FeeModel.STANDARD), float(FeeModel.EVENT)]
    if periods is None:
        periods = ["1y", "3y", "5y"]
    if timeframes is None:
        timeframes = ["daily", "weekly"]

    if cache_dir is None:
        cache_dir = os.path.join(os.path.dirname(__file__), ".grid_cache")
    os.makedirs(cache_dir, exist_ok=True)

    results = {}
    total = len(data)

    if n_jobs and n_jobs > 1:
        if progress:
            mgr = Manager()
            q = mgr.Queue()
        else:
            q = None

        with ProcessPoolExecutor(max_workers=n_jobs) as executor:
            futures = {
                executor.submit(
                    _run_symbol, sym, df, grid, capital,
                    fee_rates, top_n, periods, timeframes,
                    progress, q, cache_dir,
                    hourly_data.get(sym) if hourly_data else None,
                ): sym
                for sym, df in data.items()
            }

            if progress:
                worker_state = {}
                sym_done = 0

                def _monitor():
                    nonlocal sym_done
                    while True:
                        try:
                            msg = q.get(timeout=1)
                        except Exception:
                            continue
                        if msg is None:
                            break
                        sym_name, tf, period, label, idx, sub_total = msg
                        if tf == "DONE":
                            sym_done += 1
                            worker_state.pop(sym_name, None)
                        else:
                            worker_state[sym_name] = f"{tf}|{period}|{label} ({idx+1}/{sub_total})"
                        status_parts = [f"{s}: {st}" for s, st in sorted(worker_state.items())]
                        status = " | ".join(status_parts) if status_parts else ""
                        _print_progress(sym_done, total, status)

                mon = threading.Thread(target=_monitor, daemon=True)
                mon.start()

            for future in as_completed(futures):
                sym, sym_result = future.result()
                results[sym] = sym_result

            if progress:
                q.put(None)
                mon.join(timeout=5)
                _print_progress(total, total, "All symbols completed")
    else:
        for idx, (sym, df) in enumerate(data.items()):
            if progress:
                _print_progress(idx, total, f"Processing {sym}...")
            _, sym_result = _run_symbol(
                sym, df, grid, capital,
                fee_rates, top_n, periods, timeframes,
                progress=progress,
                cache_dir=cache_dir,
                hourly_df=hourly_data.get(sym) if hourly_data else None,
            )
            results[sym] = sym_result
            if progress:
                _print_progress(idx + 1, total, f"Completed {sym}")

    return results
