"""Experiment 4: Multi-Asset Portfolio Optimization (~500K combinations)

Self-contained numpy-based portfolio backtester.
2/3/4-asset portfolios with various weight allocations and rebalancing strategies.
IS/OOS split: 70%/30%. Multiprocessing for speed.

Optimization: pre-compute aligned price matrices per unique asset-set in main process,
then pass (is_prices, oos_prices, is_dates, oos_dates) indices to workers.
"""

import sys
import pathlib
import time
import itertools
from multiprocessing import Pool, cpu_count, shared_memory
import struct

import numpy as np
import pandas as pd

# ── Constants ──
PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
RESULTS_DIR = PROJECT_ROOT / "results"
RESULTS_DIR.mkdir(exist_ok=True)

CAPITAL = 2000.0
FEE_RATE = 0.0025  # 0.25% each way
MIN_OVERLAP_DAYS = 500
IS_RATIO = 0.70

AGGRESSIVE = [
    "TQQQ", "SPXL", "SOXL", "TNA", "QLD", "UWM", "UPRO", "TECL", "SSO", "ROM",
    "NVDA", "TSLA", "META", "AAPL", "MSFT", "GOOGL", "AMZN", "AVGO", "NFLX", "QQQ",
]
DEFENSIVE = [
    "GLD", "TLT", "BND", "XLP", "XLV", "VNQ", "XLU", "SPY", "IWM", "DIA",
]

# ── Rebalancing configs ──
REBAL_2A = [
    ("band", 0.01), ("band", 0.03), ("band", 0.05), ("band", 0.07),
    ("band", 0.10), ("band", 0.15), ("band", 0.20),
    ("monthly", 0), ("quarterly", 0), ("semi_annual", 0), ("annual", 0),
]
REBAL_3A = [
    ("band", 0.03), ("band", 0.05), ("band", 0.10), ("band", 0.15),
    ("monthly", 0), ("quarterly", 0), ("semi_annual", 0), ("annual", 0),
]
REBAL_4A = [
    ("band", 0.05), ("band", 0.10), ("band", 0.15),
    ("monthly", 0), ("quarterly", 0), ("annual", 0),
]

# ── Weight presets ──
WEIGHT_2A = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]


def resolve_3a_weights_1agg(preset_name):
    presets = {
        "equal": (1/3, 1/3, 1/3),
        "heavy_agg": (0.50, 0.25, 0.25),
        "heavy_def": (0.20, 0.40, 0.40),
        "balanced": (0.40, 0.30, 0.30),
        "agg60": (0.60, 0.20, 0.20),
        "agg70": (0.70, 0.15, 0.15),
        "agg10": (0.10, 0.45, 0.45),
        "agg80": (0.80, 0.10, 0.10),
        "def60_30": (0.10, 0.60, 0.30),
        "def50_40": (0.10, 0.50, 0.40),
    }
    return presets[preset_name]


def resolve_3a_weights_2agg(preset_name):
    presets = {
        "equal": (1/3, 1/3, 1/3),
        "heavy_agg": (0.35, 0.35, 0.30),
        "heavy_def": (0.20, 0.20, 0.60),
        "balanced": (0.30, 0.30, 0.40),
        "agg_dom": (0.40, 0.40, 0.20),
        "agg_split": (0.50, 0.30, 0.20),
        "def_dom": (0.15, 0.15, 0.70),
        "mild_agg": (0.25, 0.25, 0.50),
        "strong_agg": (0.45, 0.45, 0.10),
        "asym_agg": (0.60, 0.20, 0.20),
    }
    return presets[preset_name]


def resolve_4a_weights(preset_name):
    presets = {
        "equal": (0.25, 0.25, 0.25, 0.25),
        "aggressive_tilt": (0.35, 0.30, 0.20, 0.15),
        "defensive_tilt": (0.15, 0.20, 0.30, 0.35),
        "barbell": (0.40, 0.10, 0.10, 0.40),
        "pyramid": (0.40, 0.30, 0.20, 0.10),
    }
    return presets[preset_name]


PRESET_1AGG = ["equal", "heavy_agg", "heavy_def", "balanced", "agg60",
               "agg70", "agg10", "agg80", "def60_30", "def50_40"]
PRESET_2AGG = ["equal", "heavy_agg", "heavy_def", "balanced", "agg_dom",
               "agg_split", "def_dom", "mild_agg", "strong_agg", "asym_agg"]
PRESET_4A = ["equal", "aggressive_tilt", "defensive_tilt", "barbell", "pyramid"]


# ── Data loading & alignment ──
def load_all_close():
    """Load all close prices into a dict of {symbol: pd.Series}."""
    all_symbols = list(set(AGGRESSIVE + DEFENSIVE))
    data = {}
    for sym in all_symbols:
        path = DATA_DIR / f"{sym}.parquet"
        if not path.exists():
            print(f"  {sym}: MISSING")
            continue
        df = pd.read_parquet(path)
        s = df["close"].copy()
        s.index = pd.to_datetime(s.index)
        data[sym] = s
        print(f"  {sym}: {len(s)} days")
    return data


def align_symbols(symbols, all_close):
    """Align symbols to common dates. Returns (dates_np, prices_np) or None."""
    series_list = []
    for sym in symbols:
        if sym not in all_close:
            return None
        series_list.append(all_close[sym])

    common_idx = series_list[0].index
    for s in series_list[1:]:
        common_idx = common_idx.intersection(s.index)

    if len(common_idx) < MIN_OVERLAP_DAYS:
        return None

    common_idx = common_idx.sort_values()
    prices = np.column_stack([s.loc[common_idx].values for s in series_list])
    dates = common_idx.values.astype("datetime64[D]")
    return dates, prices


def precompute_aligned_data(all_close):
    """Pre-compute aligned price matrices for all unique asset sets."""
    print("Pre-computing aligned data for unique asset sets...")

    # Collect all unique asset sets
    asset_sets = set()

    # 2-asset
    for agg in AGGRESSIVE:
        for dfn in DEFENSIVE:
            asset_sets.add(tuple(sorted([agg, dfn])))

    # 3-asset: 1 agg + 2 def
    for agg in AGGRESSIVE:
        for d1, d2 in itertools.combinations(DEFENSIVE, 2):
            asset_sets.add(tuple(sorted([agg, d1, d2])))

    # 3-asset: 2 agg + 1 def
    for a1, a2 in itertools.combinations(AGGRESSIVE, 2):
        for dfn in DEFENSIVE:
            asset_sets.add(tuple(sorted([a1, a2, dfn])))

    # 4-asset
    for a1, a2 in itertools.combinations(AGGRESSIVE, 2):
        for d1, d2 in itertools.combinations(DEFENSIVE, 2):
            asset_sets.add(tuple(sorted([a1, a2, d1, d2])))

    print(f"  Unique asset sets: {len(asset_sets):,}")

    # Align each set
    aligned = {}
    skipped = 0
    for asset_key in asset_sets:
        # We need the alignment in the ORDER used by combos, not sorted order.
        # Store by sorted key, but align needs to be done per-combo order.
        # Actually, we'll store aligned data keyed by sorted tuple,
        # and the combo will specify its own symbol order + reorder columns.
        result = align_symbols(list(asset_key), all_close)
        if result is None:
            skipped += 1
            continue
        dates, prices = result
        split_idx = int(len(dates) * IS_RATIO)
        if split_idx < 100 or (len(dates) - split_idx) < 50:
            skipped += 1
            continue

        aligned[asset_key] = {
            "dates": dates,
            "prices": prices,
            "split_idx": split_idx,
            "symbol_order": list(asset_key),  # sorted order
        }

    print(f"  Valid: {len(aligned):,}, Skipped: {skipped}")
    return aligned


# ── Portfolio simulation (numpy) ──
def simulate_portfolio(prices, weights, rebal_type, rebal_param, months, years):
    """
    Simulate a rebalanced portfolio.
    prices: (n_days, n_assets) numpy array
    weights: tuple of target weights
    months/years: pre-computed int arrays (or None for band-only)
    Returns: (equity_curve, total_trades, rebal_count)
    """
    n_days, n_assets = prices.shape
    target_w = np.array(weights, dtype=np.float64)
    equity = np.empty(n_days, dtype=np.float64)

    # Initial allocation
    shares = np.zeros(n_assets, dtype=np.float64)
    cash = CAPITAL
    for j in range(n_assets):
        alloc = CAPITAL * target_w[j]
        shares[j] = alloc / (prices[0, j] * (1 + FEE_RATE))
        cash -= shares[j] * prices[0, j] * (1 + FEE_RATE)

    total_trades = n_assets
    rebal_count = 0

    last_rebal_month = months[0] if months is not None else -1
    last_rebal_year = years[0] if years is not None else -1

    for i in range(n_days):
        asset_values = shares * prices[i]
        total_equity = np.sum(asset_values) + cash
        equity[i] = total_equity

        if i == 0:
            continue
        if total_equity <= 0:
            equity[i:] = 0
            break

        # Check rebalance trigger
        do_rebal = False
        current_w = asset_values / total_equity

        if rebal_type == "band":
            if np.max(np.abs(current_w - target_w)) > rebal_param:
                do_rebal = True
        elif rebal_type == "monthly":
            m = months[i]
            if m != last_rebal_month:
                do_rebal = True
                last_rebal_month = m
                last_rebal_year = years[i]
        elif rebal_type == "quarterly":
            m, y = months[i], years[i]
            if (m - 1) // 3 != (last_rebal_month - 1) // 3 or y != last_rebal_year:
                do_rebal = True
                last_rebal_month = m
                last_rebal_year = y
        elif rebal_type == "semi_annual":
            m, y = months[i], years[i]
            h = 0 if m <= 6 else 1
            lh = 0 if last_rebal_month <= 6 else 1
            if h != lh or y != last_rebal_year:
                do_rebal = True
                last_rebal_month = m
                last_rebal_year = y
        elif rebal_type == "annual":
            y = years[i]
            if y != last_rebal_year:
                do_rebal = True
                last_rebal_month = months[i]
                last_rebal_year = y

        if do_rebal:
            rebal_count += 1
            sell_revenue = 0.0
            trades_this = 0
            for j in range(n_assets):
                if shares[j] > 0:
                    sell_revenue += shares[j] * prices[i, j] * (1 - FEE_RATE)
                    trades_this += 1
                    shares[j] = 0.0

            available = cash + sell_revenue
            for j in range(n_assets):
                alloc = available * target_w[j]
                shares[j] = alloc / (prices[i, j] * (1 + FEE_RATE))
                trades_this += 1

            cash = available - sum(
                shares[j] * prices[i, j] * (1 + FEE_RATE) for j in range(n_assets)
            )
            total_trades += trades_this

    return equity, total_trades, rebal_count


def compute_bh_return(prices, weights):
    """Buy-and-hold return for same assets with same initial weights."""
    n_assets = prices.shape[1]
    target_w = np.array(weights, dtype=np.float64)
    shares = np.zeros(n_assets)
    for j in range(n_assets):
        alloc = CAPITAL * target_w[j]
        shares[j] = alloc / (prices[0, j] * (1 + FEE_RATE))
    cash = CAPITAL - sum(shares[j] * prices[0, j] * (1 + FEE_RATE) for j in range(n_assets))
    final = np.sum(shares * prices[-1]) + cash
    return (final - CAPITAL) / CAPITAL


def compute_metrics(equity, dates, total_trades, rebal_count):
    """Compute performance metrics from equity curve."""
    if len(equity) < 2 or equity[0] <= 0:
        return None

    initial = equity[0]
    final = equity[-1]
    total_return = (final - initial) / initial

    days = (dates[-1] - dates[0]) / np.timedelta64(1, "D")
    yrs = days / 365.25
    if yrs <= 0:
        return None

    ann_return = (final / initial) ** (1 / yrs) - 1

    peak = np.maximum.accumulate(equity)
    dd = (equity - peak) / peak
    max_dd = float(np.min(dd))

    daily_ret = np.diff(equity) / equity[:-1]
    std = np.std(daily_ret, ddof=1) if len(daily_ret) > 1 else 0.0
    sharpe = float(np.mean(daily_ret) / std * np.sqrt(252)) if std > 0 else 0.0

    calmar = ann_return / abs(max_dd) if max_dd != 0 else 0.0

    return {
        "total_return": total_return,
        "sharpe": sharpe,
        "maxdd": max_dd,
        "calmar": calmar,
        "trades": total_trades,
        "rebal_count": rebal_count,
        "years": round(yrs, 2),
        "trades_per_year": round(total_trades / yrs, 1) if yrs > 0 else 0.0,
    }


# ── Worker function (single-process, operates on pre-aligned data) ──
def process_combo(symbols, weights, rtype, rparam, category,
                  is_prices, oos_prices, is_dates, oos_dates,
                  is_months, is_years, oos_months, oos_years):
    """Process a single combo with pre-aligned data."""

    # IS backtest
    is_eq, is_trades, is_rebal = simulate_portfolio(
        is_prices, weights, rtype, rparam, is_months, is_years
    )
    is_m = compute_metrics(is_eq, is_dates, is_trades, is_rebal)
    if is_m is None:
        return None

    # OOS backtest
    oos_eq, oos_trades, oos_rebal = simulate_portfolio(
        oos_prices, weights, rtype, rparam, oos_months, oos_years
    )
    oos_m = compute_metrics(oos_eq, oos_dates, oos_trades, oos_rebal)
    if oos_m is None:
        return None

    bh_ret = compute_bh_return(oos_prices, weights)
    rebal_label = f"band_{int(rparam*100)}%" if rtype == "band" else rtype

    return {
        "assets": "|".join(symbols),
        "n_assets": len(symbols),
        "weights": "|".join(f"{w:.3f}" for w in weights),
        "rebal_type": rtype,
        "rebal_param": rparam,
        "rebal_label": rebal_label,
        "is_return": round(is_m["total_return"], 4),
        "is_sharpe": round(is_m["sharpe"], 4),
        "is_maxdd": round(is_m["maxdd"], 4),
        "is_trades": is_m["trades"],
        "is_rebal_count": is_m["rebal_count"],
        "oos_return": round(oos_m["total_return"], 4),
        "oos_sharpe": round(oos_m["sharpe"], 4),
        "oos_maxdd": round(oos_m["maxdd"], 4),
        "oos_calmar": round(oos_m["calmar"], 4),
        "oos_trades": oos_m["trades"],
        "oos_rebal_count": oos_m["rebal_count"],
        "bh_return": round(bh_ret, 4),
        "vs_bh": round(oos_m["total_return"] - bh_ret, 4),
        "years": oos_m["years"],
        "trades_per_year": oos_m["trades_per_year"],
        "category": category,
    }


def _worker_batch(batch):
    """Process a batch. Each item is (symbols, weights, rtype, rparam, category, asset_key_idx)."""
    # Access global aligned data (set by pool initializer)
    results = []
    for symbols, weights, rtype, rparam, category, akey_idx in batch:
        ad = _ALIGNED_LIST[akey_idx]
        # Reorder columns to match symbol order
        col_indices = [ad["symbol_order"].index(s) for s in symbols]

        is_prices = ad["is_prices"][:, col_indices]
        oos_prices = ad["oos_prices"][:, col_indices]

        r = process_combo(
            symbols, weights, rtype, rparam, category,
            is_prices, oos_prices,
            ad["is_dates"], ad["oos_dates"],
            ad["is_months"], ad["is_years"],
            ad["oos_months"], ad["oos_years"],
        )
        if r is not None:
            results.append(r)
    return results


# Global for pool workers
_ALIGNED_LIST = None


def _init_worker(aligned_list):
    global _ALIGNED_LIST
    _ALIGNED_LIST = aligned_list


# ── Main ──
def main():
    t0 = time.time()

    # Load all data
    print("Loading data...")
    all_close = load_all_close()
    print(f"Loaded {len(all_close)} symbols\n")

    # Pre-compute aligned data
    aligned_raw = precompute_aligned_data(all_close)

    # Convert to indexed list for worker access
    aligned_list = []
    akey_to_idx = {}
    for akey, ad in aligned_raw.items():
        idx = len(aligned_list)
        akey_to_idx[akey] = idx

        dates = ad["dates"]
        prices = ad["prices"]
        split = ad["split_idx"]

        is_dates = dates[:split]
        oos_dates = dates[split:]
        is_prices = prices[:split]
        oos_prices = prices[split:]

        # Pre-compute months/years for calendar rebalancing
        is_pd = pd.DatetimeIndex(is_dates)
        oos_pd = pd.DatetimeIndex(oos_dates)

        aligned_list.append({
            "is_dates": is_dates,
            "oos_dates": oos_dates,
            "is_prices": is_prices,
            "oos_prices": oos_prices,
            "is_months": is_pd.month.values.astype(np.int32),
            "is_years": is_pd.year.values.astype(np.int32),
            "oos_months": oos_pd.month.values.astype(np.int32),
            "oos_years": oos_pd.year.values.astype(np.int32),
            "symbol_order": ad["symbol_order"],
        })

    del aligned_raw
    print(f"  Prepared {len(aligned_list)} aligned datasets\n")

    # Generate combos with asset_key indices
    print("Generating combinations...")
    all_combos = []

    # 2-asset
    n2 = 0
    for agg in AGGRESSIVE:
        for dfn in DEFENSIVE:
            akey = tuple(sorted([agg, dfn]))
            if akey not in akey_to_idx:
                continue
            aidx = akey_to_idx[akey]
            for agg_w in WEIGHT_2A:
                weights = (agg_w, 1 - agg_w)
                for rtype, rparam in REBAL_2A:
                    all_combos.append(([agg, dfn], weights, rtype, rparam, "2a", aidx))
                    n2 += 1

    # 3-asset: 1 agg + 2 def
    n3 = 0
    for agg in AGGRESSIVE:
        for d1, d2 in itertools.combinations(DEFENSIVE, 2):
            akey = tuple(sorted([agg, d1, d2]))
            if akey not in akey_to_idx:
                continue
            aidx = akey_to_idx[akey]
            for preset in PRESET_1AGG:
                w = resolve_3a_weights_1agg(preset)
                for rtype, rparam in REBAL_3A:
                    all_combos.append(([agg, d1, d2], w, rtype, rparam, "3a", aidx))
                    n3 += 1

    # 3-asset: 2 agg + 1 def
    for a1, a2 in itertools.combinations(AGGRESSIVE, 2):
        for dfn in DEFENSIVE:
            akey = tuple(sorted([a1, a2, dfn]))
            if akey not in akey_to_idx:
                continue
            aidx = akey_to_idx[akey]
            for preset in PRESET_2AGG:
                w = resolve_3a_weights_2agg(preset)
                for rtype, rparam in REBAL_3A:
                    all_combos.append(([a1, a2, dfn], w, rtype, rparam, "3a", aidx))
                    n3 += 1

    # 4-asset
    n4 = 0
    for a1, a2 in itertools.combinations(AGGRESSIVE, 2):
        for d1, d2 in itertools.combinations(DEFENSIVE, 2):
            akey = tuple(sorted([a1, a2, d1, d2]))
            if akey not in akey_to_idx:
                continue
            aidx = akey_to_idx[akey]
            for preset in PRESET_4A:
                w = resolve_4a_weights(preset)
                for rtype, rparam in REBAL_4A:
                    all_combos.append(([a1, a2, d1, d2], w, rtype, rparam, "4a", aidx))
                    n4 += 1

    print(f"  2-asset: {n2:,}")
    print(f"  3-asset: {n3:,}")
    print(f"  4-asset: {n4:,}")
    print(f"  Total:   {len(all_combos):,}\n")

    # Batch for multiprocessing
    n_workers = max(1, cpu_count() - 1)
    batch_size = 1000
    batches = []
    for i in range(0, len(all_combos), batch_size):
        batches.append(all_combos[i:i+batch_size])

    print(f"Processing with {n_workers} workers, {len(batches)} batches...")

    all_results = []
    processed = 0
    report_interval = 50000

    with Pool(n_workers, initializer=_init_worker, initargs=(aligned_list,)) as pool:
        for batch_result in pool.imap_unordered(_worker_batch, batches):
            all_results.extend(batch_result)
            processed += batch_size
            if processed % report_interval < batch_size:
                elapsed = time.time() - t0
                rate = processed / elapsed if elapsed > 0 else 0
                print(f"  Progress: {processed:,}/{len(all_combos):,} "
                      f"({processed/len(all_combos)*100:.1f}%) "
                      f"| {rate:.0f} combos/sec "
                      f"| results: {len(all_results):,}")

    elapsed = time.time() - t0
    print(f"\nDone! {len(all_results):,} valid results in {elapsed:.1f}s "
          f"({len(all_combos)/elapsed:.0f} combos/sec)\n")

    # Save to CSV
    df = pd.DataFrame(all_results)
    csv_path = RESULTS_DIR / "portfolio_opt_results.csv"
    df.to_csv(csv_path, index=False)
    print(f"Saved to {csv_path}\n")

    # ── Print summaries ──
    if df.empty:
        print("No valid results.")
        return

    cols_sharpe = ["assets", "weights", "rebal_label",
                   "oos_return", "oos_sharpe", "oos_maxdd", "oos_calmar",
                   "oos_trades", "oos_rebal_count",
                   "bh_return", "vs_bh", "years", "trades_per_year"]

    print("=" * 130)
    print("TOP 20 BY OOS SHARPE - 2-ASSET PORTFOLIOS")
    print("=" * 130)
    df2 = df[df["category"] == "2a"].nlargest(20, "oos_sharpe")
    if not df2.empty:
        print(df2[cols_sharpe].to_string(index=False))
    print()

    print("=" * 130)
    print("TOP 20 BY OOS SHARPE - 3-ASSET PORTFOLIOS")
    print("=" * 130)
    df3 = df[df["category"] == "3a"].nlargest(20, "oos_sharpe")
    if not df3.empty:
        print(df3[cols_sharpe].to_string(index=False))
    print()

    print("=" * 130)
    print("TOP 20 BY OOS SHARPE - 4-ASSET PORTFOLIOS")
    print("=" * 130)
    df4 = df[df["category"] == "4a"].nlargest(20, "oos_sharpe")
    if not df4.empty:
        print(df4[cols_sharpe].to_string(index=False))
    print()

    print("=" * 130)
    print("TOP 20 BY OOS CALMAR RATIO (ALL)")
    print("=" * 130)
    df_cal = df.nlargest(20, "oos_calmar")
    print(df_cal[["assets", "n_assets", "weights", "rebal_label",
                   "oos_return", "oos_sharpe", "oos_maxdd", "oos_calmar",
                   "oos_trades", "vs_bh", "years", "trades_per_year"]].to_string(index=False))
    print()

    print("=" * 130)
    print("TOP 20 BY SHARPE-TO-MAXDD TRADEOFF (OOS Sharpe / abs(OOS MaxDD))")
    print("=" * 130)
    df_v = df[df["oos_maxdd"] < 0].copy()
    if not df_v.empty:
        df_v["sharpe_mdd"] = df_v["oos_sharpe"] / df_v["oos_maxdd"].abs()
        df_top = df_v.nlargest(20, "sharpe_mdd")
        print(df_top[["assets", "n_assets", "weights", "rebal_label",
                       "oos_return", "oos_sharpe", "oos_maxdd", "sharpe_mdd",
                       "oos_trades", "vs_bh", "years", "trades_per_year"]].to_string(index=False))
    print()

    # SPXL40+GLD60 comparison
    print("=" * 130)
    print("COMPARISON: SPXL 40% + GLD 60% (band_5%)")
    print("=" * 130)
    spxl_gld = df[
        (df["assets"] == "SPXL|GLD") &
        (df["rebal_label"] == "band_5%") &
        (df["weights"].str.startswith("0.400"))
    ]
    if not spxl_gld.empty:
        print(spxl_gld[["assets", "weights", "rebal_label",
                         "is_return", "is_sharpe", "is_maxdd",
                         "oos_return", "oos_sharpe", "oos_maxdd", "oos_calmar",
                         "oos_trades", "oos_rebal_count",
                         "bh_return", "vs_bh", "years", "trades_per_year"]].to_string(index=False))
    else:
        print("SPXL|GLD 40/60 band_5% not found.")
    print()

    # Overall stats
    print("=" * 130)
    print("OVERALL STATISTICS")
    print("=" * 130)
    for cat in ["2a", "3a", "4a"]:
        sub = df[df["category"] == cat]
        if sub.empty:
            continue
        print(f"\n{cat.upper()} ({len(sub):,} combos):")
        print(f"  OOS Sharpe: mean={sub['oos_sharpe'].mean():.3f}, "
              f"median={sub['oos_sharpe'].median():.3f}, "
              f"max={sub['oos_sharpe'].max():.3f}")
        print(f"  OOS Return: mean={sub['oos_return'].mean():.3f}, "
              f"median={sub['oos_return'].median():.3f}, "
              f"max={sub['oos_return'].max():.3f}")
        print(f"  OOS MaxDD:  mean={sub['oos_maxdd'].mean():.3f}, "
              f"median={sub['oos_maxdd'].median():.3f}, "
              f"worst={sub['oos_maxdd'].min():.3f}")
        pos = (sub["vs_bh"] > 0).sum()
        print(f"  vs B&H positive: {pos}/{len(sub)} ({pos/len(sub)*100:.1f}%)")
    print()


if __name__ == "__main__":
    main()
