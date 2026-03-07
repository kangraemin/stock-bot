"""Drawdown-Based Buy Strategy Backtest

ATH 대비 X% 하락 시 매수, 다양한 탈출 조건으로 65,520 조합 테스트.
- 70 symbols x 13 drawdown levels x 6 recovery types x 12 exit types
- IS/OOS 70%/30% split
- Fee: 0.25% per trade
"""

import os
import sys
import time
import pathlib
from itertools import product
from multiprocessing import Pool, cpu_count

import numpy as np
import pandas as pd

# ── Constants ──
PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
RESULTS_DIR = PROJECT_ROOT / "results"
CAPITAL = 2000.0
FEE_RATE = 0.0025

DRAWDOWN_THRESHOLDS = [
    -0.05, -0.075, -0.10, -0.125, -0.15, -0.175,
    -0.20, -0.25, -0.30, -0.35, -0.40, -0.45, -0.50,
]
RECOVERY_TYPES = ["none", "bounce_3", "bounce_5", "bounce_7", "bounce_10", "bounce_15"]
EXIT_TYPES = [
    "hold_20d", "hold_30d", "hold_40d", "hold_60d", "hold_90d",
    "hold_120d", "hold_180d", "hold_252d",
    "rsi_exit_50", "rsi_exit_60", "rsi_exit_70",
    "new_ath",
]

BOUNCE_MAP = {
    "none": 0.0,
    "bounce_3": 0.03,
    "bounce_5": 0.05,
    "bounce_7": 0.07,
    "bounce_10": 0.10,
    "bounce_15": 0.15,
}


def compute_rsi(close, period=14):
    delta = np.diff(close, prepend=close[0])
    gain = np.maximum(delta, 0)
    loss = np.maximum(-delta, 0)
    avg_gain = np.zeros_like(close, dtype=np.float64)
    avg_loss = np.zeros_like(close, dtype=np.float64)
    if len(close) <= period:
        return np.full_like(close, 50.0)
    avg_gain[period] = np.mean(gain[1:period + 1])
    avg_loss[period] = np.mean(loss[1:period + 1])
    for i in range(period + 1, len(close)):
        avg_gain[i] = (avg_gain[i - 1] * (period - 1) + gain[i]) / period
        avg_loss[i] = (avg_loss[i - 1] * (period - 1) + loss[i]) / period
    rs = avg_gain / np.where(avg_loss == 0, 1e-10, avg_loss)
    rsi = 100 - 100 / (1 + rs)
    rsi[:period] = 50
    return rsi


def load_symbols():
    """Load all daily parquet files, skip hourly/macro/index."""
    symbols = {}
    for f in sorted(DATA_DIR.glob("*.parquet")):
        name = f.stem
        if "_1h" in name or name.startswith("^") or "=" in name:
            continue
        df = pd.read_parquet(f)
        if len(df) < 252:
            continue
        close = df["close"].values.astype(np.float64)
        symbols[name] = close
    return symbols


def run_single_backtest(close, rsi, ath, drawdown_pct, recovery_type, exit_type, capital=CAPITAL):
    """Run a single backtest on a price array. Returns equity curve and trade count."""
    n = len(close)
    bounce_pct = BOUNCE_MAP[recovery_type]

    # Parse exit type
    if exit_type.startswith("hold_"):
        hold_days = int(exit_type.split("_")[1].replace("d", ""))
        exit_mode = "hold"
        rsi_threshold = 0
    elif exit_type.startswith("rsi_exit_"):
        rsi_threshold = int(exit_type.split("_")[2])
        exit_mode = "rsi"
        hold_days = 0
    else:  # new_ath
        exit_mode = "new_ath"
        hold_days = 0
        rsi_threshold = 0

    equity = np.full(n, capital, dtype=np.float64)
    cash = capital
    shares = 0.0
    entry_idx = -1
    total_trades = 0
    local_low = np.inf
    threshold_hit = False

    for i in range(1, n):
        price = close[i]
        dd = price / ath[i] - 1.0

        if shares == 0:
            if dd <= drawdown_pct:
                if bounce_pct == 0:
                    cost = price * (1 + FEE_RATE)
                    shares = cash / cost
                    cash = 0.0
                    entry_idx = i
                    total_trades += 1
                    threshold_hit = False
                    local_low = np.inf
                else:
                    if not threshold_hit:
                        threshold_hit = True
                        local_low = price
                    else:
                        if price < local_low:
                            local_low = price
                        if local_low > 0 and (price / local_low - 1.0) >= bounce_pct:
                            cost = price * (1 + FEE_RATE)
                            shares = cash / cost
                            cash = 0.0
                            entry_idx = i
                            total_trades += 1
                            threshold_hit = False
                            local_low = np.inf
            else:
                if threshold_hit and dd > drawdown_pct:
                    threshold_hit = False
                    local_low = np.inf
                if threshold_hit and price < local_low:
                    local_low = price
        else:
            should_sell = False
            if exit_mode == "hold":
                if i - entry_idx >= hold_days:
                    should_sell = True
            elif exit_mode == "rsi":
                if rsi[i] >= rsi_threshold:
                    should_sell = True
            elif exit_mode == "new_ath":
                if price >= ath[i]:
                    should_sell = True

            if should_sell:
                cash = shares * price * (1 - FEE_RATE)
                shares = 0.0
                total_trades += 1
                entry_idx = -1

        equity[i] = cash + shares * price

    # Force close at end
    if shares > 0:
        cash = shares * close[-1] * (1 - FEE_RATE)
        shares = 0.0
        total_trades += 1
        equity[-1] = cash

    return equity, total_trades


def compute_metrics(equity, total_trades):
    """Compute return, sharpe, maxdd from equity curve."""
    if len(equity) < 2 or equity[0] == 0:
        return 0.0, 0.0, 0.0, 0

    total_return = equity[-1] / equity[0] - 1.0

    daily_ret = np.diff(equity) / equity[:-1]
    daily_ret = daily_ret[np.isfinite(daily_ret)]

    if len(daily_ret) < 2 or np.std(daily_ret) == 0:
        sharpe = 0.0
    else:
        sharpe = np.mean(daily_ret) / np.std(daily_ret) * np.sqrt(252)

    peak = np.maximum.accumulate(equity)
    dd = (equity - peak) / np.where(peak == 0, 1, peak)
    maxdd = np.min(dd)

    return total_return, sharpe, maxdd, total_trades


def process_symbol(args):
    """Process all parameter combos for a single symbol."""
    symbol, close = args
    n = len(close)
    if n < 252:
        return []

    # Precompute
    rsi = compute_rsi(close)

    # IS/OOS split
    split_idx = int(n * 0.7)
    is_close = close[:split_idx]
    is_rsi = rsi[:split_idx]
    is_ath = np.maximum.accumulate(is_close)

    oos_close = close[split_idx:]
    oos_rsi = rsi[split_idx:]
    oos_ath_start = np.max(is_close)
    oos_ath = np.maximum.accumulate(np.concatenate([[oos_ath_start], oos_close]))[1:]

    years = n / 252.0
    bh_return = close[-1] / close[0] - 1.0

    results = []
    for dd_pct, rec_type, exit_type in product(DRAWDOWN_THRESHOLDS, RECOVERY_TYPES, EXIT_TYPES):
        is_eq, is_trades = run_single_backtest(is_close, is_rsi, is_ath, dd_pct, rec_type, exit_type)
        is_ret, is_sharpe, is_maxdd, _ = compute_metrics(is_eq, is_trades)

        oos_eq, oos_trades = run_single_backtest(oos_close, oos_rsi, oos_ath, dd_pct, rec_type, exit_type)
        oos_ret, oos_sharpe, oos_maxdd, _ = compute_metrics(oos_eq, oos_trades)

        total_trades = is_trades + oos_trades
        trades_per_year = total_trades / years if years > 0 else 0

        results.append({
            "symbol": symbol,
            "drawdown_pct": dd_pct,
            "recovery_type": rec_type,
            "exit_type": exit_type,
            "is_return": round(is_ret, 6),
            "is_sharpe": round(is_sharpe, 4),
            "is_maxdd": round(is_maxdd, 4),
            "is_trades": is_trades,
            "oos_return": round(oos_ret, 6),
            "oos_sharpe": round(oos_sharpe, 4),
            "oos_maxdd": round(oos_maxdd, 4),
            "oos_trades": oos_trades,
            "bh_return": round(bh_return, 6),
            "vs_bh": round(oos_ret - bh_return, 6),
            "years": round(years, 2),
            "trades_per_year": round(trades_per_year, 2),
        })

    return results


def main():
    print("=" * 70)
    print("Drawdown-Based Buy Strategy Backtest")
    print("=" * 70)

    t0 = time.time()

    print("\nLoading data...")
    symbols = load_symbols()
    print(f"  Loaded {len(symbols)} symbols")

    total_combos = len(symbols) * len(DRAWDOWN_THRESHOLDS) * len(RECOVERY_TYPES) * len(EXIT_TYPES)
    print(f"  Total combinations: {total_combos:,}")
    print(f"  CPUs: {cpu_count()}")

    symbol_list = [(sym, close) for sym, close in symbols.items()]

    all_results = []
    done = 0
    with Pool(processes=min(cpu_count(), len(symbol_list))) as pool:
        for sym_results in pool.imap_unordered(process_symbol, symbol_list):
            all_results.extend(sym_results)
            done += 1
            count = len(all_results)
            if count % 5000 < 936 or done == len(symbol_list):
                elapsed = time.time() - t0
                print(f"  Progress: {done}/{len(symbol_list)} symbols, "
                      f"{count:,}/{total_combos:,} combos, {elapsed:.1f}s")

    df = pd.DataFrame(all_results)

    RESULTS_DIR.mkdir(exist_ok=True)
    out_path = RESULTS_DIR / "drawdown_buy_results.csv"
    df.to_csv(out_path, index=False)
    print(f"\nSaved {len(df):,} rows to {out_path}")

    print("\n" + "=" * 70)
    print("Top 20 by OOS Sharpe")
    print("=" * 70)
    top = df.nlargest(20, "oos_sharpe")
    pd.set_option("display.max_columns", 20)
    pd.set_option("display.width", 200)
    pd.set_option("display.float_format", lambda x: f"{x:.4f}")
    print(top.to_string(index=False))

    elapsed = time.time() - t0
    print(f"\nTotal time: {elapsed:.1f}s")


if __name__ == "__main__":
    main()
