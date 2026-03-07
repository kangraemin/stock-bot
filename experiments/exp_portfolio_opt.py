"""Experiment 4: Multi-Asset Portfolio Optimization (~500K combinations)

Self-contained numpy-based portfolio backtester.
2/3/4-asset portfolios with various weight allocations and rebalancing strategies.
IS/OOS split: 70%/30%.

Strategy: pre-compute all aligned data in main process, then use fork-based
multiprocessing (global data inherited, no pickling).
"""

import sys
import os
import pathlib
import time
import itertools
import multiprocessing as mp

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

WEIGHT_2A = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]

PRESET_1AGG = {
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
PRESET_2AGG = {
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
PRESET_4A = {
    "equal": (0.25, 0.25, 0.25, 0.25),
    "aggressive_tilt": (0.35, 0.30, 0.20, 0.15),
    "defensive_tilt": (0.15, 0.20, 0.30, 0.35),
    "barbell": (0.40, 0.10, 0.10, 0.40),
    "pyramid": (0.40, 0.30, 0.20, 0.10),
}

# ── Global aligned data (populated in main, inherited by fork) ──
G_ALIGNED = []  # list of dicts with pre-split, pre-computed data


# ── Portfolio simulation ──
def simulate_portfolio(prices, weights, rebal_type, rebal_param, months, years):
    n_days, n_assets = prices.shape
    target_w = np.array(weights, dtype=np.float64)
    equity = np.empty(n_days, dtype=np.float64)

    shares = np.zeros(n_assets, dtype=np.float64)
    cash = CAPITAL
    for j in range(n_assets):
        alloc = CAPITAL * target_w[j]
        shares[j] = alloc / (prices[0, j] * (1 + FEE_RATE))
        cash -= shares[j] * prices[0, j] * (1 + FEE_RATE)

    total_trades = n_assets
    rebal_count = 0
    last_rm = months[0] if months is not None else -1
    last_ry = years[0] if years is not None else -1

    for i in range(n_days):
        asset_values = shares * prices[i]
        total_eq = np.sum(asset_values) + cash
        equity[i] = total_eq

        if i == 0:
            continue
        if total_eq <= 0:
            equity[i:] = 0
            break

        do_rebal = False
        current_w = asset_values / total_eq

        if rebal_type == "band":
            if np.max(np.abs(current_w - target_w)) > rebal_param:
                do_rebal = True
        elif rebal_type == "monthly":
            if months[i] != last_rm:
                do_rebal = True
                last_rm = months[i]
                last_ry = years[i]
        elif rebal_type == "quarterly":
            m, y = months[i], years[i]
            if (m - 1) // 3 != (last_rm - 1) // 3 or y != last_ry:
                do_rebal = True
                last_rm = m
                last_ry = y
        elif rebal_type == "semi_annual":
            m, y = months[i], years[i]
            if (0 if m <= 6 else 1) != (0 if last_rm <= 6 else 1) or y != last_ry:
                do_rebal = True
                last_rm = m
                last_ry = y
        elif rebal_type == "annual":
            if years[i] != last_ry:
                do_rebal = True
                last_rm = months[i]
                last_ry = years[i]

        if do_rebal:
            rebal_count += 1
            sell_rev = 0.0
            n_trades = 0
            for j in range(n_assets):
                if shares[j] > 0:
                    sell_rev += shares[j] * prices[i, j] * (1 - FEE_RATE)
                    n_trades += 1
                    shares[j] = 0.0
            avail = cash + sell_rev
            for j in range(n_assets):
                shares[j] = (avail * target_w[j]) / (prices[i, j] * (1 + FEE_RATE))
                n_trades += 1
            cash = avail - sum(shares[j] * prices[i, j] * (1 + FEE_RATE) for j in range(n_assets))
            total_trades += n_trades

    return equity, total_trades, rebal_count


def compute_bh_return(prices, weights):
    n_assets = prices.shape[1]
    tw = np.array(weights, dtype=np.float64)
    shares = np.zeros(n_assets)
    for j in range(n_assets):
        shares[j] = (CAPITAL * tw[j]) / (prices[0, j] * (1 + FEE_RATE))
    cash = CAPITAL - sum(shares[j] * prices[0, j] * (1 + FEE_RATE) for j in range(n_assets))
    return (np.sum(shares * prices[-1]) + cash - CAPITAL) / CAPITAL


def compute_metrics(equity, dates, total_trades, rebal_count):
    if len(equity) < 2 or equity[0] <= 0:
        return None
    initial, final = equity[0], equity[-1]
    total_return = (final - initial) / initial
    days = (dates[-1] - dates[0]) / np.timedelta64(1, "D")
    yrs = days / 365.25
    if yrs <= 0:
        return None
    ann_ret = (final / initial) ** (1 / yrs) - 1
    peak = np.maximum.accumulate(equity)
    max_dd = float(np.min((equity - peak) / peak))
    dr = np.diff(equity) / equity[:-1]
    std = np.std(dr, ddof=1) if len(dr) > 1 else 0.0
    sharpe = float(np.mean(dr) / std * np.sqrt(252)) if std > 0 else 0.0
    calmar = ann_ret / abs(max_dd) if max_dd != 0 else 0.0
    return {
        "total_return": total_return, "sharpe": sharpe, "maxdd": max_dd,
        "calmar": calmar, "trades": total_trades, "rebal_count": rebal_count,
        "years": round(yrs, 2), "trades_per_year": round(total_trades / yrs, 1) if yrs > 0 else 0,
    }


def _worker_batch(batch):
    """Process batch. Each item: (symbols, weights, rtype, rparam, category, aidx, col_indices)"""
    results = []
    for symbols, weights, rtype, rparam, category, aidx, col_idx in batch:
        ad = G_ALIGNED[aidx]
        is_p = ad["is_prices"][:, col_idx]
        oos_p = ad["oos_prices"][:, col_idx]

        is_eq, is_tr, is_rb = simulate_portfolio(is_p, weights, rtype, rparam, ad["is_m"], ad["is_y"])
        is_met = compute_metrics(is_eq, ad["is_d"], is_tr, is_rb)
        if is_met is None:
            continue

        oos_eq, oos_tr, oos_rb = simulate_portfolio(oos_p, weights, rtype, rparam, ad["oos_m"], ad["oos_y"])
        oos_met = compute_metrics(oos_eq, ad["oos_d"], oos_tr, oos_rb)
        if oos_met is None:
            continue

        bh = compute_bh_return(oos_p, weights)
        rl = f"band_{int(rparam*100)}%" if rtype == "band" else rtype

        results.append({
            "assets": "|".join(symbols),
            "n_assets": len(symbols),
            "weights": "|".join(f"{w:.3f}" for w in weights),
            "rebal_type": rtype, "rebal_param": rparam, "rebal_label": rl,
            "is_return": round(is_met["total_return"], 4),
            "is_sharpe": round(is_met["sharpe"], 4),
            "is_maxdd": round(is_met["maxdd"], 4),
            "is_trades": is_met["trades"],
            "is_rebal_count": is_met["rebal_count"],
            "oos_return": round(oos_met["total_return"], 4),
            "oos_sharpe": round(oos_met["sharpe"], 4),
            "oos_maxdd": round(oos_met["maxdd"], 4),
            "oos_calmar": round(oos_met["calmar"], 4),
            "oos_trades": oos_met["trades"],
            "oos_rebal_count": oos_met["rebal_count"],
            "bh_return": round(bh, 4),
            "vs_bh": round(oos_met["total_return"] - bh, 4),
            "years": oos_met["years"],
            "trades_per_year": oos_met["trades_per_year"],
            "category": category,
        })
    return results


def main():
    global G_ALIGNED

    t0 = time.time()

    # Load all data
    print("Loading data...")
    all_close = {}
    for sym in set(AGGRESSIVE + DEFENSIVE):
        path = DATA_DIR / f"{sym}.parquet"
        if not path.exists():
            print(f"  {sym}: MISSING")
            continue
        df = pd.read_parquet(path)
        s = df["close"].copy()
        s.index = pd.to_datetime(s.index)
        all_close[sym] = s
        print(f"  {sym}: {len(s)} days")
    print(f"Loaded {len(all_close)} symbols\n")

    # Pre-compute all unique aligned datasets
    print("Pre-computing aligned data...")
    asset_sets = set()
    for agg in AGGRESSIVE:
        for dfn in DEFENSIVE:
            asset_sets.add(tuple(sorted([agg, dfn])))
    for agg in AGGRESSIVE:
        for d1, d2 in itertools.combinations(DEFENSIVE, 2):
            asset_sets.add(tuple(sorted([agg, d1, d2])))
    for a1, a2 in itertools.combinations(AGGRESSIVE, 2):
        for dfn in DEFENSIVE:
            asset_sets.add(tuple(sorted([a1, a2, dfn])))
    for a1, a2 in itertools.combinations(AGGRESSIVE, 2):
        for d1, d2 in itertools.combinations(DEFENSIVE, 2):
            asset_sets.add(tuple(sorted([a1, a2, d1, d2])))

    print(f"  Unique asset sets: {len(asset_sets):,}")

    akey_to_idx = {}
    skipped = 0
    for akey in asset_sets:
        series_list = []
        skip = False
        for sym in akey:
            if sym not in all_close:
                skip = True
                break
            series_list.append(all_close[sym])
        if skip:
            skipped += 1
            continue

        common_idx = series_list[0].index
        for s in series_list[1:]:
            common_idx = common_idx.intersection(s.index)
        if len(common_idx) < MIN_OVERLAP_DAYS:
            skipped += 1
            continue

        common_idx = common_idx.sort_values()
        prices = np.column_stack([s.loc[common_idx].values for s in series_list])
        dates = common_idx.values.astype("datetime64[D]")
        split = int(len(dates) * IS_RATIO)
        if split < 100 or (len(dates) - split) < 50:
            skipped += 1
            continue

        is_pd = pd.DatetimeIndex(dates[:split])
        oos_pd = pd.DatetimeIndex(dates[split:])

        idx = len(G_ALIGNED)
        akey_to_idx[akey] = idx
        G_ALIGNED.append({
            "is_d": dates[:split], "oos_d": dates[split:],
            "is_prices": prices[:split].astype(np.float64),
            "oos_prices": prices[split:].astype(np.float64),
            "is_m": is_pd.month.values.astype(np.int32),
            "is_y": is_pd.year.values.astype(np.int32),
            "oos_m": oos_pd.month.values.astype(np.int32),
            "oos_y": oos_pd.year.values.astype(np.int32),
            "sym_order": list(akey),  # sorted
        })

    print(f"  Valid: {len(G_ALIGNED):,}, Skipped: {skipped}")
    del all_close  # free memory
    print(f"  Aligned data ready ({time.time()-t0:.1f}s)\n")

    # Generate combos: (symbols, weights, rtype, rparam, category, aidx, col_indices)
    print("Generating combinations...")
    all_combos = []
    n2 = n3 = n4 = 0

    # 2-asset
    for agg in AGGRESSIVE:
        for dfn in DEFENSIVE:
            akey = tuple(sorted([agg, dfn]))
            if akey not in akey_to_idx:
                continue
            aidx = akey_to_idx[akey]
            sym_order = G_ALIGNED[aidx]["sym_order"]
            col_idx = [sym_order.index(agg), sym_order.index(dfn)]
            for agg_w in WEIGHT_2A:
                for rt, rp in REBAL_2A:
                    all_combos.append(([agg, dfn], (agg_w, 1-agg_w), rt, rp, "2a", aidx, col_idx))
                    n2 += 1

    # 3-asset: 1 agg + 2 def
    for agg in AGGRESSIVE:
        for d1, d2 in itertools.combinations(DEFENSIVE, 2):
            akey = tuple(sorted([agg, d1, d2]))
            if akey not in akey_to_idx:
                continue
            aidx = akey_to_idx[akey]
            sym_order = G_ALIGNED[aidx]["sym_order"]
            col_idx = [sym_order.index(agg), sym_order.index(d1), sym_order.index(d2)]
            for pname, w in PRESET_1AGG.items():
                for rt, rp in REBAL_3A:
                    all_combos.append(([agg, d1, d2], w, rt, rp, "3a", aidx, col_idx))
                    n3 += 1

    # 3-asset: 2 agg + 1 def
    for a1, a2 in itertools.combinations(AGGRESSIVE, 2):
        for dfn in DEFENSIVE:
            akey = tuple(sorted([a1, a2, dfn]))
            if akey not in akey_to_idx:
                continue
            aidx = akey_to_idx[akey]
            sym_order = G_ALIGNED[aidx]["sym_order"]
            col_idx = [sym_order.index(a1), sym_order.index(a2), sym_order.index(dfn)]
            for pname, w in PRESET_2AGG.items():
                for rt, rp in REBAL_3A:
                    all_combos.append(([a1, a2, dfn], w, rt, rp, "3a", aidx, col_idx))
                    n3 += 1

    # 4-asset
    for a1, a2 in itertools.combinations(AGGRESSIVE, 2):
        for d1, d2 in itertools.combinations(DEFENSIVE, 2):
            akey = tuple(sorted([a1, a2, d1, d2]))
            if akey not in akey_to_idx:
                continue
            aidx = akey_to_idx[akey]
            sym_order = G_ALIGNED[aidx]["sym_order"]
            col_idx = [sym_order.index(a1), sym_order.index(a2),
                       sym_order.index(d1), sym_order.index(d2)]
            for pname, w in PRESET_4A.items():
                for rt, rp in REBAL_4A:
                    all_combos.append(([a1, a2, d1, d2], w, rt, rp, "4a", aidx, col_idx))
                    n4 += 1

    print(f"  2-asset: {n2:,}")
    print(f"  3-asset: {n3:,}")
    print(f"  4-asset: {n4:,}")
    print(f"  Total:   {len(all_combos):,}\n")

    # Batch
    batch_size = 1000
    batches = [all_combos[i:i+batch_size] for i in range(0, len(all_combos), batch_size)]
    n_workers = max(1, mp.cpu_count() - 1)
    print(f"Processing with {n_workers} workers (fork), {len(batches)} batches...")
    sys.stdout.flush()

    all_results = []
    processed = 0

    # Use fork to inherit G_ALIGNED without pickling
    ctx = mp.get_context("fork")
    with ctx.Pool(n_workers) as pool:
        for batch_result in pool.imap_unordered(_worker_batch, batches):
            all_results.extend(batch_result)
            processed += batch_size
            if processed % 50000 < batch_size:
                elapsed = time.time() - t0
                rate = processed / elapsed if elapsed > 0 else 0
                print(f"  Progress: {processed:,}/{len(all_combos):,} "
                      f"({processed/len(all_combos)*100:.1f}%) "
                      f"| {rate:.0f}/s | results: {len(all_results):,}")
                sys.stdout.flush()

    elapsed = time.time() - t0
    print(f"\nDone! {len(all_results):,} valid results in {elapsed:.1f}s "
          f"({len(all_combos)/elapsed:.0f} combos/sec)\n")

    # Save
    df = pd.DataFrame(all_results)
    csv_path = RESULTS_DIR / "portfolio_opt_results.csv"
    df.to_csv(csv_path, index=False)
    print(f"Saved to {csv_path}\n")

    if df.empty:
        print("No valid results.")
        return

    # ── Summaries ──
    cols = ["assets", "weights", "rebal_label",
            "oos_return", "oos_sharpe", "oos_maxdd", "oos_calmar",
            "oos_trades", "oos_rebal_count",
            "bh_return", "vs_bh", "years", "trades_per_year"]

    for cat, label in [("2a", "2-ASSET"), ("3a", "3-ASSET"), ("4a", "4-ASSET")]:
        print("=" * 130)
        print(f"TOP 20 BY OOS SHARPE - {label} PORTFOLIOS")
        print("=" * 130)
        sub = df[df["category"] == cat].nlargest(20, "oos_sharpe")
        if not sub.empty:
            print(sub[cols].to_string(index=False))
        print()

    print("=" * 130)
    print("TOP 20 BY OOS CALMAR RATIO (ALL)")
    print("=" * 130)
    print(df.nlargest(20, "oos_calmar")[
        ["assets", "n_assets", "weights", "rebal_label",
         "oos_return", "oos_sharpe", "oos_maxdd", "oos_calmar",
         "oos_trades", "vs_bh", "years", "trades_per_year"]
    ].to_string(index=False))
    print()

    print("=" * 130)
    print("TOP 20 SHARPE-TO-MAXDD (OOS Sharpe / abs(MaxDD))")
    print("=" * 130)
    dv = df[df["oos_maxdd"] < 0].copy()
    if not dv.empty:
        dv["s2m"] = dv["oos_sharpe"] / dv["oos_maxdd"].abs()
        print(dv.nlargest(20, "s2m")[
            ["assets", "n_assets", "weights", "rebal_label",
             "oos_return", "oos_sharpe", "oos_maxdd", "s2m",
             "oos_trades", "vs_bh", "years", "trades_per_year"]
        ].to_string(index=False))
    print()

    # SPXL40+GLD60 comparison
    print("=" * 130)
    print("COMPARISON: SPXL 40% + GLD 60% (band_5%)")
    print("=" * 130)
    sg = df[(df["assets"] == "SPXL|GLD") &
            (df["rebal_label"] == "band_5%") &
            (df["weights"].str.startswith("0.400"))]
    if not sg.empty:
        print(sg[["assets", "weights", "rebal_label",
                   "is_return", "is_sharpe", "is_maxdd",
                   "oos_return", "oos_sharpe", "oos_maxdd", "oos_calmar",
                   "oos_trades", "oos_rebal_count",
                   "bh_return", "vs_bh", "years", "trades_per_year"]].to_string(index=False))
    else:
        print("Not found in results.")
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
              f"median={sub['oos_sharpe'].median():.3f}, max={sub['oos_sharpe'].max():.3f}")
        print(f"  OOS Return: mean={sub['oos_return'].mean():.3f}, "
              f"median={sub['oos_return'].median():.3f}, max={sub['oos_return'].max():.3f}")
        print(f"  OOS MaxDD:  mean={sub['oos_maxdd'].mean():.3f}, "
              f"median={sub['oos_maxdd'].median():.3f}, worst={sub['oos_maxdd'].min():.3f}")
        pos = (sub["vs_bh"] > 0).sum()
        print(f"  vs B&H positive: {pos}/{len(sub)} ({pos/len(sub)*100:.1f}%)")
    print()


if __name__ == "__main__":
    main()
