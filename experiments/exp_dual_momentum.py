"""
Experiment 1: Dual Momentum Rotation Backtest
Gary Antonacci style dual momentum with grid search over ~92K combinations.

- Single pair rotation: aggressive x defensive x lookback x freq x momentum_type
- Pool rotation: top-N from full pool with defensive fallback
"""

import os
import sys
import time
import glob
import warnings
from itertools import product
from multiprocessing import Pool, cpu_count

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# ── Config ──
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
RESULTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "results")
CAPITAL = 2000
FEE = 0.0025  # round-trip fee
MIN_DAYS = 1000  # minimum data length for aggressive assets

DEFENSIVE_SYMBOLS = ["GLD", "TLT", "BND", "XLP", "XLV", "VNQ", "XLU", "SPY", "IWM", "DIA"]
LOOKBACK_MONTHS = list(range(1, 13))  # 1..12
TRADING_DAYS_PER_MONTH = 21
ROTATION_FREQS = {
    "weekly": 5,
    "biweekly": 10,
    "monthly": 21,
    "quarterly": 63,
}
MOMENTUM_TYPES = ["absolute", "relative", "dual"]
IS_RATIO = 0.70  # 70% in-sample


# ── Inline metrics (numpy, no pandas in hot path) ──
def compute_metrics_inline(equity: np.ndarray, total_trades: int = 0) -> dict:
    """Fast numpy metrics."""
    if len(equity) < 2 or equity[0] == 0:
        return {"total_return": 0.0, "annualized_return": 0.0, "max_drawdown": 0.0,
                "sharpe_ratio": 0.0, "total_trades": total_trades}

    initial = equity[0]
    final = equity[-1]
    total_return = (final - initial) / initial

    n_days = len(equity)
    years = n_days / 252.0
    if years > 0 and initial > 0:
        annualized_return = (final / initial) ** (1.0 / years) - 1.0
    else:
        annualized_return = 0.0

    peak = np.maximum.accumulate(equity)
    drawdown = (equity - peak) / np.where(peak > 0, peak, 1.0)
    max_drawdown = float(np.min(drawdown))

    daily_returns = np.diff(equity) / equity[:-1]
    std = np.std(daily_returns, ddof=1) if len(daily_returns) > 1 else 0.0
    if std > 0:
        sharpe_ratio = float(np.mean(daily_returns) / std * np.sqrt(252))
    else:
        sharpe_ratio = 0.0

    return {
        "total_return": total_return,
        "annualized_return": annualized_return,
        "max_drawdown": max_drawdown,
        "sharpe_ratio": sharpe_ratio,
        "total_trades": total_trades,
    }


# ── Data loading ──
def load_all_data():
    """Load all daily parquet files, return dict of symbol -> (dates, close_prices)."""
    data = {}
    files = sorted(glob.glob(os.path.join(DATA_DIR, "*.parquet")))
    for f in files:
        if "_1h" in f:
            continue
        sym = os.path.basename(f).replace(".parquet", "")
        # Skip non-tradeable indices/futures
        if sym.startswith("^") or "=" in sym or sym == "DX-Y.NYB":
            continue
        try:
            df = pd.read_parquet(f)
            # Support both capital and lowercase column names
            close_col = "Close" if "Close" in df.columns else "close" if "close" in df.columns else None
            if close_col is None:
                continue
            close = df[close_col].dropna().values.astype(np.float64)
            dates = df.index.values
            if len(close) >= 50:
                data[sym] = (dates[:len(close)], close)
        except Exception:
            continue
    return data


def get_overlapping(dates_a, close_a, dates_b, close_b):
    """Find overlapping date range and return aligned close arrays."""
    # Convert to int64 for fast intersection
    da = dates_a.astype("int64")
    db = dates_b.astype("int64")
    common = np.intersect1d(da, db)
    if len(common) < 100:
        return None, None, None
    mask_a = np.isin(da, common)
    mask_b = np.isin(db, common)
    return common, close_a[mask_a], close_b[mask_b]


# ── Single pair rotation backtest ──
def run_single_pair(close_agg, close_def, lookback_days, rotation_days, momentum_type, capital=CAPITAL):
    """
    Run dual momentum rotation between aggressive and defensive asset.
    Returns (equity_curve, n_trades).
    """
    n = len(close_agg)
    if n < lookback_days + rotation_days + 1:
        return None, 0

    equity = np.full(n, capital, dtype=np.float64)
    position = 0  # 0=cash, 1=aggressive, -1=defensive
    n_trades = 0
    shares = 0.0
    entry_price = 0.0

    start = lookback_days
    # Build rotation schedule
    rotation_dates = list(range(start, n, rotation_days))

    for i in range(start, n):
        # Update equity based on current position
        if position == 1:
            equity[i] = equity[i - 1] + shares * (close_agg[i] - close_agg[i - 1])
        elif position == -1:
            equity[i] = equity[i - 1] + shares * (close_def[i] - close_def[i - 1])
        else:
            equity[i] = equity[i - 1]

        # Check rotation
        if i in rotation_dates:
            ret_agg = (close_agg[i] - close_agg[i - lookback_days]) / close_agg[i - lookback_days]
            ret_def = (close_def[i] - close_def[i - lookback_days]) / close_def[i - lookback_days]

            if momentum_type == "relative":
                new_pos = 1 if ret_agg >= ret_def else -1
            elif momentum_type == "absolute":
                new_pos = 1 if ret_agg > 0 else -1
            else:  # dual
                if ret_agg > 0 and ret_agg >= ret_def:
                    new_pos = 1
                else:
                    new_pos = -1

            if new_pos != position:
                # Apply fee
                current_eq = equity[i]
                current_eq *= (1.0 - FEE)
                equity[i] = current_eq
                n_trades += 1

                if new_pos == 1:
                    shares = current_eq / close_agg[i]
                else:
                    shares = current_eq / close_def[i]
                position = new_pos

    return equity[start:], n_trades


# ── Worker for single pair ──
def worker_single_pair(args):
    """Multiprocessing worker for single pair rotation."""
    (sym_agg, sym_def, lookback_m, freq_name, freq_days, mom_type,
     close_agg_is, close_def_is, close_agg_oos, close_def_oos,
     close_agg_full, bh_return_is, bh_return_oos, years_is, years_oos) = args

    lookback_days = lookback_m * TRADING_DAYS_PER_MONTH

    # IS
    eq_is, trades_is = run_single_pair(close_agg_is, close_def_is, lookback_days, freq_days, mom_type)
    if eq_is is None or len(eq_is) < 2:
        return None

    m_is = compute_metrics_inline(eq_is, trades_is)

    # OOS
    eq_oos, trades_oos = run_single_pair(close_agg_oos, close_def_oos, lookback_days, freq_days, mom_type)
    if eq_oos is None or len(eq_oos) < 2:
        return None

    m_oos = compute_metrics_inline(eq_oos, trades_oos)

    total_trades = trades_is + trades_oos
    total_years = years_is + years_oos

    return {
        "symbol": sym_agg,
        "defensive": sym_def,
        "lookback_months": lookback_m,
        "rotation_freq": freq_name,
        "momentum_type": mom_type,
        "is_return": round(m_is["total_return"] * 100, 2),
        "is_sharpe": round(m_is["sharpe_ratio"], 3),
        "is_maxdd": round(m_is["max_drawdown"] * 100, 2),
        "is_trades": trades_is,
        "oos_return": round(m_oos["total_return"] * 100, 2),
        "oos_sharpe": round(m_oos["sharpe_ratio"], 3),
        "oos_maxdd": round(m_oos["max_drawdown"] * 100, 2),
        "oos_trades": trades_oos,
        "bh_return": round(bh_return_oos * 100, 2),
        "vs_bh": round((m_oos["total_return"] - bh_return_oos) * 100, 2),
        "years": round(total_years, 1),
        "trades_per_year": round(total_trades / total_years, 1) if total_years > 0 else 0,
    }


# ── Pool rotation backtest ──
def run_pool_rotation(all_close, sym_indices, def_idx, lookback_days, rotation_days,
                      momentum_type, top_n, capital=CAPITAL):
    """
    Run dual momentum rotation across a pool of assets.
    all_close: (n_symbols, n_days) array
    sym_indices: indices of aggressive symbols
    def_idx: index of defensive symbol
    Returns (equity_curve, n_trades).
    """
    n_days = all_close.shape[1]
    if n_days < lookback_days + rotation_days + 1:
        return None, 0

    equity = np.full(n_days, capital, dtype=np.float64)
    # Track allocation: array of (symbol_idx, weight, shares)
    current_alloc = []  # list of (sym_idx, shares)
    n_trades = 0

    start = lookback_days
    rotation_dates_set = set(range(start, n_days, rotation_days))

    for i in range(start, n_days):
        # Update equity
        daily_pnl = 0.0
        for sym_idx, sh in current_alloc:
            daily_pnl += sh * (all_close[sym_idx, i] - all_close[sym_idx, i - 1])
        equity[i] = equity[i - 1] + daily_pnl

        if i in rotation_dates_set:
            # Compute returns for all aggressive symbols
            rets = {}
            for si in sym_indices:
                if all_close[si, i - lookback_days] > 0:
                    rets[si] = (all_close[si, i] - all_close[si, i - lookback_days]) / all_close[si, i - lookback_days]

            if not rets:
                continue

            # Sort by return descending
            sorted_syms = sorted(rets.keys(), key=lambda s: rets[s], reverse=True)

            # Select top-N
            if momentum_type == "relative":
                selected = sorted_syms[:top_n]
            elif momentum_type == "absolute":
                selected = [s for s in sorted_syms[:top_n] if rets[s] > 0]
                if not selected:
                    selected = [def_idx]
            else:  # dual
                candidates = [s for s in sorted_syms[:top_n] if rets[s] > 0]
                if candidates:
                    selected = candidates
                else:
                    selected = [def_idx]

            # Check if allocation changed
            current_set = set(s for s, _ in current_alloc)
            new_set = set(selected)
            if current_set != new_set:
                current_eq = equity[i] * (1.0 - FEE)
                equity[i] = current_eq
                n_trades += 1

                weight = 1.0 / len(selected)
                current_alloc = []
                for si in selected:
                    alloc_capital = current_eq * weight
                    sh = alloc_capital / all_close[si, i] if all_close[si, i] > 0 else 0
                    current_alloc.append((si, sh))

    return equity[start:], n_trades


def worker_pool_rotation(args):
    """Multiprocessing worker for pool rotation."""
    (lookback_m, freq_name, freq_days, mom_type, top_n,
     all_close_is, all_close_oos, agg_indices, def_idx,
     years_is, years_oos, bh_return_oos, sym_names) = args

    lookback_days = lookback_m * TRADING_DAYS_PER_MONTH

    eq_is, trades_is = run_pool_rotation(
        all_close_is, agg_indices, def_idx, lookback_days, freq_days, mom_type, top_n)
    if eq_is is None or len(eq_is) < 2:
        return None
    m_is = compute_metrics_inline(eq_is, trades_is)

    eq_oos, trades_oos = run_pool_rotation(
        all_close_oos, agg_indices, def_idx, lookback_days, freq_days, mom_type, top_n)
    if eq_oos is None or len(eq_oos) < 2:
        return None
    m_oos = compute_metrics_inline(eq_oos, trades_oos)

    total_trades = trades_is + trades_oos
    total_years = years_is + years_oos

    return {
        "symbol": f"POOL_top{top_n}",
        "defensive": sym_names[def_idx],
        "lookback_months": lookback_m,
        "rotation_freq": freq_name,
        "momentum_type": mom_type,
        "is_return": round(m_is["total_return"] * 100, 2),
        "is_sharpe": round(m_is["sharpe_ratio"], 3),
        "is_maxdd": round(m_is["max_drawdown"] * 100, 2),
        "is_trades": trades_is,
        "oos_return": round(m_oos["total_return"] * 100, 2),
        "oos_sharpe": round(m_oos["sharpe_ratio"], 3),
        "oos_maxdd": round(m_oos["max_drawdown"] * 100, 2),
        "oos_trades": trades_oos,
        "bh_return": round(bh_return_oos * 100, 2),
        "vs_bh": round((m_oos["total_return"] - bh_return_oos) * 100, 2),
        "years": round(total_years, 1),
        "trades_per_year": round(total_trades / total_years, 1) if total_years > 0 else 0,
    }


def main():
    t0 = time.time()
    print("=" * 80)
    print("Experiment 1: Dual Momentum Rotation Backtest")
    print("=" * 80)

    # Load data
    print("\n[1/5] Loading data...")
    all_data = load_all_data()
    print(f"  Loaded {len(all_data)} symbols")

    # Filter aggressive assets (>= MIN_DAYS)
    aggressive_syms = sorted([s for s, (d, c) in all_data.items() if len(c) >= MIN_DAYS])
    defensive_syms = [s for s in DEFENSIVE_SYMBOLS if s in all_data]
    print(f"  Aggressive assets (>={MIN_DAYS} days): {len(aggressive_syms)}")
    print(f"  Defensive assets available: {len(defensive_syms)} -> {defensive_syms}")

    # ── Part 1: Single pair rotation ──
    print("\n[2/5] Preparing single pair combinations...")
    tasks = []
    skipped = 0

    for sym_agg in aggressive_syms:
        dates_a, close_a = all_data[sym_agg]
        for sym_def in defensive_syms:
            if sym_agg == sym_def:
                continue
            dates_d, close_d = all_data[sym_def]

            # Align dates
            common, ca, cd = get_overlapping(dates_a, close_a, dates_d, close_d)
            if common is None:
                skipped += 1
                continue

            n = len(ca)
            split = int(n * IS_RATIO)
            if split < 252 or (n - split) < 126:
                skipped += 1
                continue

            ca_is, ca_oos = ca[:split], ca[split:]
            cd_is, cd_oos = cd[:split], cd[split:]

            years_is = split / 252.0
            years_oos = (n - split) / 252.0

            bh_is = (ca_is[-1] - ca_is[0]) / ca_is[0] if ca_is[0] > 0 else 0
            bh_oos = (ca_oos[-1] - ca_oos[0]) / ca_oos[0] if ca_oos[0] > 0 else 0

            for lookback_m in LOOKBACK_MONTHS:
                for freq_name, freq_days in ROTATION_FREQS.items():
                    for mom_type in MOMENTUM_TYPES:
                        tasks.append((
                            sym_agg, sym_def, lookback_m, freq_name, freq_days, mom_type,
                            ca_is, cd_is, ca_oos, cd_oos,
                            ca, bh_is, bh_oos, years_is, years_oos
                        ))

    total_single = len(tasks)
    print(f"  Single pair combinations: {total_single:,} (skipped {skipped} pairs)")

    # Run single pair with multiprocessing
    print(f"\n[3/5] Running single pair backtest ({total_single:,} combos, {cpu_count()} cores)...")
    results = []
    batch_size = 5000
    n_batches = (total_single + batch_size - 1) // batch_size

    with Pool(processes=cpu_count()) as pool:
        for batch_idx in range(n_batches):
            start_idx = batch_idx * batch_size
            end_idx = min(start_idx + batch_size, total_single)
            batch = tasks[start_idx:end_idx]

            batch_results = pool.map(worker_single_pair, batch, chunksize=100)
            valid = [r for r in batch_results if r is not None]
            results.extend(valid)

            elapsed = time.time() - t0
            done = end_idx
            if done % 10000 < batch_size or batch_idx == n_batches - 1:
                print(f"  Progress: {done:,}/{total_single:,} ({done*100/total_single:.1f}%) "
                      f"valid={len(results):,} elapsed={elapsed:.0f}s")

    print(f"  Single pair results: {len(results):,}")

    # ── Part 2: Pool rotation ──
    print("\n[4/5] Running pool rotation backtest...")

    # Build aligned matrix for pool rotation
    # Use symbols that have enough overlapping data
    pool_syms = sorted(set(aggressive_syms) | set(defensive_syms))
    # Find common date range across ALL pool symbols
    # Use pairwise approach: find dates present in at least 80% of symbols
    all_dates_sets = []
    for sym in pool_syms:
        if sym in all_data:
            d, _ = all_data[sym]
            all_dates_sets.append(set(d.astype("int64")))

    if all_dates_sets:
        # Find dates present in all symbols
        common_dates = all_dates_sets[0]
        for ds in all_dates_sets[1:]:
            common_dates &= ds
        common_dates = np.array(sorted(common_dates))

        if len(common_dates) > 500:
            sym_names = pool_syms
            n_syms = len(sym_names)
            n_days = len(common_dates)

            # Build close matrix
            all_close = np.zeros((n_syms, n_days), dtype=np.float64)
            sym_to_idx = {}
            for idx, sym in enumerate(sym_names):
                d, c = all_data[sym]
                d_int = d.astype("int64")
                mask = np.isin(d_int, common_dates)
                all_close[idx] = c[mask][:n_days]
                sym_to_idx[sym] = idx

            split = int(n_days * IS_RATIO)
            all_close_is = all_close[:, :split]
            all_close_oos = all_close[:, split:]
            years_is = split / 252.0
            years_oos = (n_days - split) / 252.0

            # B&H for SPY as baseline
            spy_idx = sym_to_idx.get("SPY", 0)
            bh_oos = (all_close_oos[spy_idx, -1] - all_close_oos[spy_idx, 0]) / all_close_oos[spy_idx, 0] \
                if all_close_oos[spy_idx, 0] > 0 else 0

            agg_indices = [sym_to_idx[s] for s in aggressive_syms if s in sym_to_idx]

            pool_tasks = []
            top_ns = [1, 3, 5]
            for def_sym in defensive_syms:
                if def_sym not in sym_to_idx:
                    continue
                def_idx = sym_to_idx[def_sym]
                for lookback_m in LOOKBACK_MONTHS:
                    for freq_name, freq_days in ROTATION_FREQS.items():
                        for mom_type in MOMENTUM_TYPES:
                            for top_n in top_ns:
                                pool_tasks.append((
                                    lookback_m, freq_name, freq_days, mom_type, top_n,
                                    all_close_is, all_close_oos, agg_indices, def_idx,
                                    years_is, years_oos, bh_oos, sym_names
                                ))

            total_pool = len(pool_tasks)
            print(f"  Pool rotation combinations: {total_pool:,}")

            pool_results = []
            with Pool(processes=cpu_count()) as mp_pool:
                batch_results = mp_pool.map(worker_pool_rotation, pool_tasks, chunksize=50)
                pool_results = [r for r in batch_results if r is not None]

            print(f"  Pool rotation results: {len(pool_results):,}")
            results.extend(pool_results)
        else:
            print(f"  Not enough common dates for pool rotation ({len(common_dates)})")
    else:
        print("  No data for pool rotation")

    # ── Save results ──
    print(f"\n[5/5] Saving results... (total: {len(results):,})")
    os.makedirs(RESULTS_DIR, exist_ok=True)

    df = pd.DataFrame(results)
    csv_path = os.path.join(RESULTS_DIR, "dual_momentum_results.csv")
    df.to_csv(csv_path, index=False)
    print(f"  Saved to {csv_path}")

    # ── Summary ──
    elapsed = time.time() - t0
    print(f"\n{'=' * 80}")
    print(f"COMPLETED in {elapsed:.1f}s ({elapsed/60:.1f}min)")
    print(f"Total combinations tested: {len(results):,}")
    print(f"{'=' * 80}")

    # Top 20 by OOS Sharpe
    if len(df) > 0:
        df_sorted = df.sort_values("oos_sharpe", ascending=False)
        print(f"\n--- Top 20 by OOS Sharpe ---")
        cols = ["symbol", "defensive", "lookback_months", "rotation_freq", "momentum_type",
                "oos_return", "oos_sharpe", "oos_maxdd", "oos_trades",
                "bh_return", "vs_bh", "years", "trades_per_year"]
        print(df_sorted[cols].head(20).to_string(index=False))

        # Summary stats
        print(f"\n--- Summary Statistics ---")
        print(f"Total results: {len(df):,}")
        print(f"OOS Sharpe > 0: {(df['oos_sharpe'] > 0).sum():,} ({(df['oos_sharpe'] > 0).mean()*100:.1f}%)")
        print(f"OOS Sharpe > 0.5: {(df['oos_sharpe'] > 0.5).sum():,} ({(df['oos_sharpe'] > 0.5).mean()*100:.1f}%)")
        print(f"OOS Sharpe > 1.0: {(df['oos_sharpe'] > 1.0).sum():,} ({(df['oos_sharpe'] > 1.0).mean()*100:.1f}%)")
        print(f"Beat B&H (vs_bh > 0): {(df['vs_bh'] > 0).sum():,} ({(df['vs_bh'] > 0).mean()*100:.1f}%)")

        print(f"\n--- OOS Sharpe by Momentum Type ---")
        for mt in MOMENTUM_TYPES:
            sub = df[df["momentum_type"] == mt]
            print(f"  {mt:10s}: mean={sub['oos_sharpe'].mean():.3f}, "
                  f"median={sub['oos_sharpe'].median():.3f}, "
                  f"max={sub['oos_sharpe'].max():.3f}, "
                  f"beat_bh={((sub['vs_bh'] > 0).mean()*100):.1f}%")

        print(f"\n--- OOS Sharpe by Rotation Frequency ---")
        for fn in ROTATION_FREQS:
            sub = df[df["rotation_freq"] == fn]
            print(f"  {fn:12s}: mean={sub['oos_sharpe'].mean():.3f}, "
                  f"median={sub['oos_sharpe'].median():.3f}, "
                  f"max={sub['oos_sharpe'].max():.3f}")

        print(f"\n--- OOS Sharpe by Lookback Period ---")
        for lb in LOOKBACK_MONTHS:
            sub = df[df["lookback_months"] == lb]
            print(f"  {lb:2d}m: mean={sub['oos_sharpe'].mean():.3f}, "
                  f"median={sub['oos_sharpe'].median():.3f}, "
                  f"max={sub['oos_sharpe'].max():.3f}")

        print(f"\n--- Top 10 Defensive Assets by avg OOS Sharpe ---")
        def_stats = df.groupby("defensive")["oos_sharpe"].agg(["mean", "median", "count"])
        def_stats = def_stats.sort_values("mean", ascending=False)
        print(def_stats.head(10).to_string())

        # IS vs OOS correlation
        corr = df[["is_sharpe", "oos_sharpe"]].corr().iloc[0, 1]
        print(f"\n--- IS/OOS Correlation ---")
        print(f"  IS Sharpe vs OOS Sharpe correlation: {corr:.3f}")

    return df


if __name__ == "__main__":
    df = main()
