#!/usr/bin/env python3
"""
Experiment 3: Lead-Lag Analysis + Pair Trading
- Phase 1: Lagged cross-correlation for all C(70,2) symbol pairs
- Phase 2: Trading signal generation & backtest for top 100 pairs
Self-contained (no imports from backtest/).
"""

import os
import sys
import time
import warnings
from itertools import combinations
from multiprocessing import Pool, cpu_count
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

warnings.filterwarnings("ignore")

PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_DIR / "data"
RESULTS_DIR = PROJECT_DIR / "results"
RESULTS_DIR.mkdir(exist_ok=True)

# --- Parameters ---
LAG_PERIODS = [1, 2, 3, 4, 5, 7, 10, 14, 20, 30]
ROLLING_WINDOWS = [20, 40, 60, 120, 252]
MIN_OVERLAP_DAYS = 252
IS_RATIO = 0.70  # first 70% in-sample
FEE_PCT = 0.0025  # 0.25% per trade
CAPITAL = 2000
THRESHOLDS = [0.01, 0.02, 0.03, 0.05, 0.07]
HOLD_DAYS = [1, 3, 5, 10, 20]
TOP_N_PAIRS = 100
CORR_STABILITY_THRESHOLD = 0.3


def load_all_daily_data():
    """Load all daily parquet files, return dict of symbol -> DataFrame."""
    data = {}
    for f in sorted(DATA_DIR.glob("*.parquet")):
        if "_1h" in f.stem:
            continue
        sym = f.stem
        df = pd.read_parquet(f)
        if "close" not in df.columns:
            continue
        if len(df) < MIN_OVERLAP_DAYS:
            continue
        data[sym] = df[["close"]].copy()
    print(f"Loaded {len(data)} daily symbols")
    return data


def compute_returns(data: dict):
    """Compute daily returns for all symbols."""
    returns = {}
    for sym, df in data.items():
        ret = df["close"].pct_change().dropna()
        returns[sym] = ret
    return returns


def compute_pair_correlations(args):
    """Compute lagged cross-correlations for a single pair."""
    sym_a, sym_b, ret_a, ret_b = args
    # Align on common dates
    common_idx = ret_a.index.intersection(ret_b.index)
    n_overlap = len(common_idx)
    if n_overlap < MIN_OVERLAP_DAYS:
        return []

    ra = ret_a.loc[common_idx].values
    rb = ret_b.loc[common_idx].values
    dates = common_idx

    results = []
    for lag in LAG_PERIODS:
        if lag >= n_overlap:
            continue
        # A leads B: correlate A[:-lag] with B[lag:]
        a_vals = ra[:n_overlap - lag]
        b_vals = rb[lag:]

        if len(a_vals) < 30:
            continue

        # Full-period correlation
        corr, p_val = stats.pearsonr(a_vals, b_vals)

        # Stability: % of rolling windows where |corr| > threshold
        stability_scores = []
        for window in ROLLING_WINDOWS:
            if window > len(a_vals):
                continue
            n_windows = len(a_vals) - window + 1
            count_above = 0
            # Sample windows for speed (every 5th)
            step = max(1, n_windows // 200)
            sampled = 0
            for i in range(0, n_windows, step):
                a_w = a_vals[i:i + window]
                b_w = b_vals[i:i + window]
                if np.std(a_w) < 1e-10 or np.std(b_w) < 1e-10:
                    continue
                r = np.corrcoef(a_w, b_w)[0, 1]
                if abs(r) > CORR_STABILITY_THRESHOLD:
                    count_above += 1
                sampled += 1
            stab = count_above / max(sampled, 1)
            stability_scores.append(stab)

        avg_stability = np.mean(stability_scores) if stability_scores else 0.0

        results.append({
            "symbol_a": sym_a,
            "symbol_b": sym_b,
            "lag": lag,
            "correlation": round(corr, 6),
            "p_value": round(p_val, 8),
            "stability": round(avg_stability, 4),
            "n_overlap_days": n_overlap,
        })

    return results


def phase1_correlations(returns: dict):
    """Phase 1: Compute lead-lag correlations for all pairs."""
    symbols = sorted(returns.keys())
    pairs = list(combinations(symbols, 2))
    print(f"Phase 1: {len(pairs)} pairs x {len(LAG_PERIODS)} lags")

    # Prepare args - both directions (A leads B, B leads A)
    args_list = []
    for sym_a, sym_b in pairs:
        args_list.append((sym_a, sym_b, returns[sym_a], returns[sym_b]))
        args_list.append((sym_b, sym_a, returns[sym_b], returns[sym_a]))

    print(f"Total correlation tasks: {len(args_list)} (both directions)")

    n_workers = max(1, cpu_count() - 1)
    print(f"Using {n_workers} workers")

    all_results = []
    start = time.time()

    with Pool(n_workers) as pool:
        batch_size = 100
        for i in range(0, len(args_list), batch_size):
            batch = args_list[i:i + batch_size]
            batch_results = pool.map(compute_pair_correlations, batch)
            for res in batch_results:
                all_results.extend(res)
            done = min(i + batch_size, len(args_list))
            elapsed = time.time() - start
            pct = done / len(args_list) * 100
            print(f"  Phase 1 progress: {done}/{len(args_list)} ({pct:.0f}%) - {elapsed:.1f}s", end="\r")

    print(f"\nPhase 1 done: {len(all_results)} correlation records in {time.time() - start:.1f}s")

    df = pd.DataFrame(all_results)
    out_path = RESULTS_DIR / "lead_lag_correlations.csv"
    df.to_csv(out_path, index=False)
    print(f"Saved to {out_path}")
    return df


def select_top_pairs(corr_df: pd.DataFrame):
    """Select top N pairs by stability * abs(correlation)."""
    corr_df = corr_df.copy()
    corr_df["score"] = corr_df["stability"] * corr_df["correlation"].abs()
    # Group by (symbol_a, symbol_b) and take the best lag
    best = corr_df.loc[corr_df.groupby(["symbol_a", "symbol_b"])["score"].idxmax()]
    best = best.sort_values("score", ascending=False).head(TOP_N_PAIRS)
    print(f"\nSelected top {len(best)} lead-lag pairs")
    return best


def backtest_lead_lag_signal(leader_ret, follower_ret, follower_close,
                              lag, threshold, hold_days, is_ratio):
    """
    Backtest a lead-lag trading signal.
    When leader return > threshold, go long follower for hold_days.
    When leader return < -threshold, go short follower for hold_days.
    """
    common_idx = leader_ret.index.intersection(follower_ret.index)
    common_idx = common_idx.intersection(follower_close.index)
    if len(common_idx) < MIN_OVERLAP_DAYS:
        return None

    leader_r = leader_ret.loc[common_idx].values
    follower_c = follower_close.loc[common_idx].values
    n = len(common_idx)

    is_end = int(n * is_ratio)

    results = {}
    for period_name, start_idx, end_idx in [("is", 0, is_end), ("oos", is_end, n)]:
        equity = CAPITAL
        trades = 0
        returns_list = []

        peak = equity
        max_dd = 0.0

        i = start_idx
        while i < end_idx - hold_days - lag:
            # Leader signal at time i
            lr = leader_r[i]
            if abs(lr) < threshold:
                i += 1
                continue

            # Enter at i + lag, exit at i + lag + hold_days
            entry_idx = i + lag
            exit_idx = min(i + lag + hold_days, end_idx - 1)
            if exit_idx >= n or entry_idx >= n:
                i += 1
                continue

            entry_price = follower_c[entry_idx]
            exit_price = follower_c[exit_idx]

            if entry_price <= 0:
                i += 1
                continue

            # Direction: leader up -> long follower, leader down -> short follower
            if lr > threshold:
                trade_ret = (exit_price / entry_price) - 1.0
            else:
                trade_ret = 1.0 - (exit_price / entry_price)

            # Apply fees
            trade_ret -= 2 * FEE_PCT  # entry + exit

            equity *= (1 + trade_ret)
            returns_list.append(trade_ret)
            trades += 1

            peak = max(peak, equity)
            dd = (peak - equity) / peak if peak > 0 else 0
            max_dd = max(max_dd, dd)

            # Skip to after this trade exits
            i = exit_idx + 1

        total_return = (equity / CAPITAL - 1) * 100
        n_days = end_idx - start_idx
        years = n_days / 252

        # Buy & hold for follower
        bh_start = follower_c[start_idx]
        bh_end = follower_c[min(end_idx - 1, n - 1)]
        bh_return = ((bh_end / bh_start) - 1) * 100 if bh_start > 0 else 0

        # Sharpe
        if returns_list and len(returns_list) > 1:
            avg_ret = np.mean(returns_list)
            std_ret = np.std(returns_list, ddof=1)
            sharpe = (avg_ret / std_ret) * np.sqrt(252 / max(hold_days, 1)) if std_ret > 0 else 0
        else:
            sharpe = 0

        results[f"{period_name}_return"] = round(total_return, 2)
        results[f"{period_name}_sharpe"] = round(sharpe, 4)
        results[f"{period_name}_maxdd"] = round(max_dd * 100, 2)
        results[f"{period_name}_trades"] = trades
        results[f"{period_name}_trades_yr"] = round(trades / max(years, 0.1), 1)

        if period_name == "is":
            results["bh_return_is"] = round(bh_return, 2)
        else:
            results["bh_return"] = round(bh_return, 2)
            results["vs_bh"] = round(total_return - bh_return, 2)

    return results


def phase2_trading(corr_df: pd.DataFrame, data: dict, returns: dict):
    """Phase 2: Generate and backtest trading signals."""
    top_pairs = select_top_pairs(corr_df)

    print(f"Phase 2: {len(top_pairs)} pairs x {len(THRESHOLDS)} thresholds x {len(HOLD_DAYS)} hold periods")
    total_combos = len(top_pairs) * len(THRESHOLDS) * len(HOLD_DAYS)
    print(f"Total combos: {total_combos}")

    all_results = []
    start = time.time()
    done = 0

    for _, row in top_pairs.iterrows():
        leader = row["symbol_a"]
        follower = row["symbol_b"]
        best_lag = int(row["lag"])
        corr_val = row["correlation"]
        stab_val = row["stability"]

        if leader not in returns or follower not in returns:
            continue
        if leader not in data or follower not in data:
            continue

        leader_ret = returns[leader]
        follower_ret = returns[follower]
        follower_close = data[follower]["close"]

        for threshold in THRESHOLDS:
            for hold in HOLD_DAYS:
                result = backtest_lead_lag_signal(
                    leader_ret, follower_ret, follower_close,
                    best_lag, threshold, hold, IS_RATIO
                )
                done += 1

                if result is None:
                    continue

                result.update({
                    "leader": leader,
                    "follower": follower,
                    "lag": best_lag,
                    "threshold": threshold,
                    "hold_days": hold,
                    "correlation": corr_val,
                    "stability": stab_val,
                })
                all_results.append(result)

                if done % 100 == 0:
                    elapsed = time.time() - start
                    pct = done / total_combos * 100
                    print(f"  Phase 2 progress: {done}/{total_combos} ({pct:.0f}%) - {elapsed:.1f}s", end="\r")

    print(f"\nPhase 2 done: {len(all_results)} trading results in {time.time() - start:.1f}s")

    df = pd.DataFrame(all_results)
    out_path = RESULTS_DIR / "lead_lag_trading.csv"
    df.to_csv(out_path, index=False)
    print(f"Saved to {out_path}")
    return df


def print_summary(corr_df: pd.DataFrame, trade_df: pd.DataFrame):
    """Print summary tables."""
    print("\n" + "=" * 100)
    print("LEAD-LAG ANALYSIS SUMMARY")
    print("=" * 100)

    # --- Top 20 most stable lead-lag relationships ---
    print("\n--- Top 20 Most Stable Lead-Lag Relationships ---")
    corr_df_copy = corr_df.copy()
    corr_df_copy["score"] = corr_df_copy["stability"] * corr_df_copy["correlation"].abs()
    best_per_pair = corr_df_copy.loc[
        corr_df_copy.groupby(["symbol_a", "symbol_b"])["score"].idxmax()
    ]
    top20_stable = best_per_pair.nlargest(20, "score")

    print(f"{'Leader':<10} {'Follower':<10} {'Lag':>4} {'Corr':>8} {'p-value':>12} "
          f"{'Stability':>10} {'Score':>8} {'Overlap':>8}")
    print("-" * 80)
    for _, r in top20_stable.iterrows():
        print(f"{r['symbol_a']:<10} {r['symbol_b']:<10} {r['lag']:>4} "
              f"{r['correlation']:>8.4f} {r['p_value']:>12.6f} "
              f"{r['stability']:>10.4f} {r['score']:>8.4f} {r['n_overlap_days']:>8}")

    # --- Top 20 trading strategies by OOS Sharpe ---
    if len(trade_df) > 0 and "oos_sharpe" in trade_df.columns:
        print("\n--- Top 20 Trading Strategies by OOS Sharpe ---")
        # Filter for minimum trades
        viable = trade_df[trade_df["oos_trades"] >= 5].copy()
        if len(viable) == 0:
            viable = trade_df.copy()

        top20_oos = viable.nlargest(20, "oos_sharpe")
        n_years = None

        print(f"{'Leader':<8} {'Follower':<8} {'Lag':>4} {'Thr':>5} {'Hold':>5} "
              f"{'IS_Ret%':>8} {'OOS_Ret%':>9} {'OOS_Shrp':>9} {'OOS_MDD%':>9} "
              f"{'OOS_Trd':>8} {'Trd/yr':>7} {'B&H%':>7} {'vsB&H':>7}")
        print("-" * 120)
        for _, r in top20_oos.iterrows():
            print(f"{r['leader']:<8} {r['follower']:<8} {r['lag']:>4} "
                  f"{r['threshold']:>5.2f} {r['hold_days']:>5} "
                  f"{r['is_return']:>8.1f} {r['oos_return']:>9.1f} "
                  f"{r['oos_sharpe']:>9.4f} {r['oos_maxdd']:>9.1f} "
                  f"{r['oos_trades']:>8} {r.get('oos_trades_yr', 0):>7.1f} "
                  f"{r['bh_return']:>7.1f} {r['vs_bh']:>7.1f}")

    # --- Pairs where leader predicts follower 3+ days ahead ---
    print("\n--- Pairs Where Leader Predicts Follower 3+ Days Ahead (lag >= 3) ---")
    long_lag = corr_df_copy[
        (corr_df_copy["lag"] >= 3) &
        (corr_df_copy["stability"] > 0.2) &
        (corr_df_copy["correlation"].abs() > 0.1)
    ].copy()
    long_lag["score"] = long_lag["stability"] * long_lag["correlation"].abs()
    long_lag_best = long_lag.loc[
        long_lag.groupby(["symbol_a", "symbol_b"])["score"].idxmax()
    ].nlargest(20, "score")

    if len(long_lag_best) > 0:
        print(f"{'Leader':<10} {'Follower':<10} {'Lag':>4} {'Corr':>8} "
              f"{'Stability':>10} {'Score':>8}")
        print("-" * 60)
        for _, r in long_lag_best.iterrows():
            print(f"{r['symbol_a']:<10} {r['symbol_b']:<10} {r['lag']:>4} "
                  f"{r['correlation']:>8.4f} {r['stability']:>10.4f} "
                  f"{r['score']:>8.4f}")
    else:
        print("  No significant long-lag relationships found.")

    # --- Overall stats ---
    print("\n--- Overall Statistics ---")
    print(f"Total correlation records: {len(corr_df)}")
    print(f"Significant correlations (p < 0.05): {len(corr_df[corr_df['p_value'] < 0.05])}")
    print(f"High stability (> 0.3): {len(corr_df[corr_df['stability'] > 0.3])}")
    if len(trade_df) > 0:
        print(f"Total trading strategies tested: {len(trade_df)}")
        if "oos_return" in trade_df.columns:
            profitable = trade_df[trade_df["oos_return"] > 0]
            print(f"OOS profitable strategies: {len(profitable)} ({len(profitable)/max(len(trade_df),1)*100:.1f}%)")
            beats_bh = trade_df[trade_df["vs_bh"] > 0] if "vs_bh" in trade_df.columns else pd.DataFrame()
            print(f"Strategies beating B&H: {len(beats_bh)} ({len(beats_bh)/max(len(trade_df),1)*100:.1f}%)")


def main():
    print("=" * 60)
    print("Experiment 3: Lead-Lag Analysis + Pair Trading")
    print("=" * 60)
    total_start = time.time()

    # Load data
    data = load_all_daily_data()
    returns = compute_returns(data)
    symbols = sorted(returns.keys())
    n_pairs = len(symbols) * (len(symbols) - 1) // 2
    print(f"Symbols: {len(symbols)}, Pairs: {n_pairs}")
    print(f"Lag periods: {LAG_PERIODS}")
    print(f"Rolling windows: {ROLLING_WINDOWS}")
    print(f"Timeframe: daily | IS/OOS split: {IS_RATIO*100:.0f}%/{(1-IS_RATIO)*100:.0f}%")
    print()

    # Phase 1
    corr_df = phase1_correlations(returns)

    # Phase 2
    trade_df = phase2_trading(corr_df, data, returns)

    # Summary
    print_summary(corr_df, trade_df)

    total_elapsed = time.time() - total_start
    print(f"\nTotal runtime: {total_elapsed:.1f}s ({total_elapsed/60:.1f}min)")


if __name__ == "__main__":
    main()
