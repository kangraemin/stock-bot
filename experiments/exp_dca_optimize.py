"""Experiment 5: DCA Optimization Backtest (~35K combinations)

Dollar-Cost Averaging with RSI-weighted amounts.
- 70 daily symbols × 4 frequencies × 5 RSI schemes × 5 RSI periods × 5 boost mults
- IS/OOS split: first 70% / last 30%
- Self-contained (no imports from backtest/)
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
DATA_DIR = pathlib.Path(__file__).resolve().parent.parent / "data"
RESULTS_DIR = pathlib.Path(__file__).resolve().parent.parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)

INITIAL_CAPITAL = 2000.0
DCA_AMOUNT = 100.0
FEE_RATE = 0.0025  # 0.25%
MIN_DAYS = 252

# ── Parameter Grid ──
FREQUENCIES = [1, 5, 10, 21]  # daily, weekly, bi-weekly, monthly
FREQ_LABELS = {1: "daily", 5: "weekly", 10: "biweekly", 21: "monthly"}

RSI_SCHEMES = ["none", "linear", "threshold", "tiered", "inverse_sigmoid"]
RSI_PERIODS = [7, 14, 21, 30, 50]
BOOST_MULTS = [1.0, 1.5, 2.0, 3.0, 5.0]

# ── Leveraged / Index / Individual classification ──
LEVERAGED = {
    "SOXL", "TQQQ", "SPXL", "QLD", "UPRO", "TECL", "TNA", "SSO", "UWM",
    "ROM", "FNGU", "NVDL", "GGLL", "BITU", "BITX", "MSTU", "ETHU",
}
INDEX_ETF = {
    "SPY", "QQQ", "VOO", "VTI", "DIA", "IWM", "SOXX", "XLK", "XLP",
    "XLU", "XLV", "GLD", "TLT", "BND", "VNQ",
}


def classify_symbol(sym):
    if sym in LEVERAGED:
        return "leveraged"
    elif sym in INDEX_ETF:
        return "index"
    else:
        return "individual"


# ── RSI Computation (numpy) ──
def compute_rsi(close, period):
    """Wilder's RSI using EMA."""
    delta = np.diff(close, prepend=close[0])
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)

    alpha = 1.0 / period
    n = len(close)
    avg_gain = np.zeros(n)
    avg_loss = np.zeros(n)

    # seed with SMA
    if n < period + 1:
        return np.full(n, 50.0)

    avg_gain[period] = np.mean(gain[1 : period + 1])
    avg_loss[period] = np.mean(loss[1 : period + 1])

    for i in range(period + 1, n):
        avg_gain[i] = avg_gain[i - 1] * (1 - alpha) + gain[i] * alpha
        avg_loss[i] = avg_loss[i - 1] * (1 - alpha) + loss[i] * alpha

    rs = np.divide(avg_gain, avg_loss, out=np.ones(n), where=avg_loss != 0)
    rsi = 100.0 - 100.0 / (1.0 + rs)
    rsi[:period] = 50.0  # neutral before enough data
    return rsi


# ── Weight Multiplier Functions ──
def weight_none(rsi_val, boost_mult):
    return 1.0


def weight_linear(rsi_val, boost_mult):
    # amount × (100 - RSI) / 50: 2x at RSI=0, 1x at RSI=50, 0x at RSI=100
    w = (100.0 - rsi_val) / 50.0
    return max(w, 0.0)


def weight_threshold(rsi_val, boost_mult):
    # full amount × boost_mult if RSI < 50, else skip
    # threshold is fixed at 50 (RSI < 50 → buy, else skip)
    if rsi_val < 50.0:
        return boost_mult
    return 0.0


def weight_tiered(rsi_val, boost_mult):
    if rsi_val < 20:
        return 3.0
    elif rsi_val < 30:
        return 2.0
    elif rsi_val < 40:
        return 1.5
    elif rsi_val < 50:
        return 1.0
    else:
        return 0.5


def weight_inverse_sigmoid(rsi_val, boost_mult):
    # Smooth curve: heavy at low RSI, light at high RSI
    # Maps RSI 0→~3x, RSI 50→~1x, RSI 100→~0.05x
    x = (rsi_val - 50.0) / 15.0
    w = 2.0 / (1.0 + np.exp(x))
    return max(w, 0.0)


WEIGHT_FNS = {
    "none": weight_none,
    "linear": weight_linear,
    "threshold": weight_threshold,
    "tiered": weight_tiered,
    "inverse_sigmoid": weight_inverse_sigmoid,
}


# ── DCA Backtest Core ──
def run_dca_backtest(close, rsi, frequency, scheme, boost_mult):
    """
    Run DCA backtest on a price series.

    Returns: (final_value, total_invested, equity_curve, n_trades)
    """
    n = len(close)
    weight_fn = WEIGHT_FNS[scheme]

    cash = INITIAL_CAPITAL
    shares = 0.0
    total_invested = INITIAL_CAPITAL
    n_trades = 0
    equity = np.zeros(n)

    for i in range(n):
        # Check if this is a DCA day
        if i > 0 and i % frequency == 0:
            w = weight_fn(rsi[i], boost_mult)
            amount = DCA_AMOUNT * w
            if amount > 0:
                cost = amount * (1.0 + FEE_RATE)
                shares_bought = amount / (close[i] * (1.0 + FEE_RATE))
                shares += shares_bought
                total_invested += amount
                n_trades += 1

        equity[i] = cash + shares * close[i]

    # Cash is always INITIAL_CAPITAL (we never spend from cash, DCA is new money)
    # Actually, let's fix the logic: initial capital buys shares on day 0
    # Re-think: initial_capital is in cash, DCA adds new money that buys shares
    # The equity = cash (initial, untouched) + shares * price
    # But that doesn't make sense for "investing". Let me re-do:
    # Day 0: invest initial_capital into shares
    # Then DCA days: add DCA_AMOUNT (new external money) to buy more shares

    # Let me redo properly:
    shares = 0.0
    total_invested = INITIAL_CAPITAL
    n_trades = 0

    # Day 0: invest initial capital
    shares = INITIAL_CAPITAL / (close[0] * (1.0 + FEE_RATE))
    n_trades += 1

    for i in range(n):
        # DCA contribution (skip day 0, already invested)
        if i > 0 and i % frequency == 0:
            w = weight_fn(rsi[i], boost_mult)
            amount = DCA_AMOUNT * w
            if amount > 0:
                shares += amount / (close[i] * (1.0 + FEE_RATE))
                total_invested += amount
                n_trades += 1

        equity[i] = shares * close[i]

    final_value = equity[-1]
    return final_value, total_invested, equity, n_trades


def compute_metrics(equity, total_invested, n_days):
    """Compute key metrics from equity curve."""
    ret = (equity[-1] - total_invested) / total_invested if total_invested > 0 else 0.0

    # Daily returns for Sharpe
    daily_ret = np.diff(equity) / np.where(equity[:-1] != 0, equity[:-1], 1.0)
    daily_ret = daily_ret[np.isfinite(daily_ret)]
    if len(daily_ret) > 1 and np.std(daily_ret) > 0:
        sharpe = np.mean(daily_ret) / np.std(daily_ret) * np.sqrt(252)
    else:
        sharpe = 0.0

    # MaxDD
    running_max = np.maximum.accumulate(equity)
    dd = (equity - running_max) / np.where(running_max != 0, running_max, 1.0)
    maxdd = np.min(dd)

    return ret, sharpe, maxdd


def lump_sum_return(close, total_invested):
    """If all DCA money was invested at day 0."""
    shares = total_invested / (close[0] * (1.0 + FEE_RATE))
    final = shares * close[-1]
    return (final - total_invested) / total_invested


# ── Worker Function ──
def process_symbol(args):
    """Process all parameter combos for a single symbol."""
    sym, close, rsi_cache, is_end_idx = args
    n = len(close)
    results = []

    close_is = close[:is_end_idx]
    close_oos = close[is_end_idx:]

    for freq, scheme, rsi_period, boost_mult in product(
        FREQUENCIES, RSI_SCHEMES, RSI_PERIODS, BOOST_MULTS
    ):
        rsi_full = rsi_cache[rsi_period]
        rsi_is = rsi_full[:is_end_idx]
        rsi_oos = rsi_full[is_end_idx:]

        if len(close_is) < MIN_DAYS or len(close_oos) < 60:
            continue

        # IS backtest
        is_val, is_invested, is_eq, is_trades = run_dca_backtest(
            close_is, rsi_is, freq, scheme, boost_mult
        )
        is_ret, is_sharpe, is_maxdd = compute_metrics(is_eq, is_invested, len(close_is))
        is_ls_ret = lump_sum_return(close_is, is_invested)

        # OOS backtest
        oos_val, oos_invested, oos_eq, oos_trades = run_dca_backtest(
            close_oos, rsi_oos, freq, scheme, boost_mult
        )
        oos_ret, oos_sharpe, oos_maxdd = compute_metrics(oos_eq, oos_invested, len(close_oos))
        oos_ls_ret = lump_sum_return(close_oos, oos_invested)

        # Fixed DCA baseline (scheme=none, same freq/period)
        fix_val, fix_inv, fix_eq, fix_trades = run_dca_backtest(
            close_oos, rsi_oos, freq, "none", 1.0
        )
        fix_ret = (fix_val - fix_inv) / fix_inv if fix_inv > 0 else 0.0

        total_years = len(close) / 252.0
        oos_years = len(close_oos) / 252.0

        results.append({
            "symbol": sym,
            "frequency": FREQ_LABELS[freq],
            "rsi_scheme": scheme,
            "rsi_period": rsi_period,
            "boost_mult": boost_mult,
            "is_return": round(is_ret, 6),
            "is_sharpe": round(is_sharpe, 4),
            "is_maxdd": round(is_maxdd, 4),
            "is_trades": is_trades,
            "is_total_invested": round(is_invested, 2),
            "oos_return": round(oos_ret, 6),
            "oos_sharpe": round(oos_sharpe, 4),
            "oos_maxdd": round(oos_maxdd, 4),
            "oos_trades": oos_trades,
            "oos_total_invested": round(oos_invested, 2),
            "lump_sum_return": round(oos_ls_ret, 6),
            "vs_lump_sum": round(oos_ret - oos_ls_ret, 6),
            "vs_fixed_dca": round(oos_ret - fix_ret, 6),
            "years": round(total_years, 2),
            "trades_per_year": round((is_trades + oos_trades) / total_years, 2) if total_years > 0 else 0,
        })

    return results


# ── Load Symbols ──
def load_symbols():
    """Load all daily parquet files, skip <252 days, return dict."""
    symbols = {}
    for f in sorted(DATA_DIR.glob("*.parquet")):
        name = f.stem
        if "_1h" in name or name.startswith("^") or "=" in name:
            continue
        df = pd.read_parquet(f)
        if len(df) < MIN_DAYS:
            print(f"  Skip {name}: only {len(df)} days")
            continue
        close = df["close"].values.astype(np.float64)
        symbols[name] = close
    return symbols


def main():
    t0 = time.time()
    print("=" * 70)
    print("Experiment 5: DCA Optimization (~35K combinations)")
    print("=" * 70)

    # Load data
    print("\n[1/3] Loading symbols...")
    symbols = load_symbols()
    print(f"  Loaded {len(symbols)} symbols")

    # Precompute RSI for all symbols and periods
    print("\n[2/3] Precomputing RSI & running grid...")
    total_combos = len(symbols) * len(FREQUENCIES) * len(RSI_SCHEMES) * len(RSI_PERIODS) * len(BOOST_MULTS)
    print(f"  Total combinations: {total_combos:,}")

    # Prepare worker args
    worker_args = []
    for sym, close in symbols.items():
        is_end_idx = int(len(close) * 0.7)
        rsi_cache = {}
        for period in RSI_PERIODS:
            rsi_cache[period] = compute_rsi(close, period)
        worker_args.append((sym, close, rsi_cache, is_end_idx))

    # Run with multiprocessing
    n_workers = max(1, cpu_count() - 1)
    print(f"  Using {n_workers} workers")

    all_results = []
    done = 0
    with Pool(n_workers) as pool:
        for result_batch in pool.imap_unordered(process_symbol, worker_args):
            all_results.extend(result_batch)
            done += 1
            if done % 5 == 0 or done == len(worker_args):
                print(f"  Progress: {done}/{len(worker_args)} symbols "
                      f"({len(all_results):,} results) "
                      f"[{time.time()-t0:.1f}s]")

    # Save results
    print(f"\n[3/3] Saving {len(all_results):,} results...")
    df = pd.DataFrame(all_results)
    out_path = RESULTS_DIR / "dca_optimize_results.csv"
    df.to_csv(out_path, index=False)
    print(f"  Saved to {out_path}")

    # ── Summary ──
    elapsed = time.time() - t0
    print(f"\n{'='*70}")
    print(f"Completed in {elapsed:.1f}s")
    print(f"{'='*70}")

    if df.empty:
        print("No results generated.")
        return

    # Top 20 by OOS Sharpe
    print("\n" + "=" * 70)
    print("TOP 20 by OOS Sharpe")
    print("=" * 70)
    top20 = df.nlargest(20, "oos_sharpe")
    cols = ["symbol", "frequency", "rsi_scheme", "rsi_period", "boost_mult",
            "oos_return", "oos_sharpe", "oos_maxdd", "oos_trades",
            "vs_lump_sum", "vs_fixed_dca", "years", "trades_per_year"]
    print(top20[cols].to_string(index=False))

    # Which RSI scheme wins most often?
    print("\n" + "=" * 70)
    print("BEST RSI SCHEME PER SYMBOL (by OOS Sharpe)")
    print("=" * 70)
    best_per_sym = df.loc[df.groupby("symbol")["oos_sharpe"].idxmax()]
    scheme_wins = best_per_sym["rsi_scheme"].value_counts()
    print(scheme_wins.to_string())
    print(f"\nWinner: {scheme_wins.index[0]} ({scheme_wins.iloc[0]} symbols)")

    # Optimal DCA frequency by symbol type
    print("\n" + "=" * 70)
    print("OPTIMAL FREQUENCY BY SYMBOL TYPE")
    print("=" * 70)
    df["sym_type"] = df["symbol"].apply(classify_symbol)
    for stype in ["leveraged", "index", "individual"]:
        sub = df[df["sym_type"] == stype]
        if sub.empty:
            continue
        best = sub.loc[sub.groupby("symbol")["oos_sharpe"].idxmax()]
        freq_dist = best["frequency"].value_counts()
        print(f"\n  {stype.upper()} ({len(best)} symbols):")
        print(f"  {freq_dist.to_dict()}")

    # RSI-weighted vs Fixed DCA win rate
    print("\n" + "=" * 70)
    print("RSI-WEIGHTED vs FIXED DCA")
    print("=" * 70)
    weighted = df[df["rsi_scheme"] != "none"]
    if not weighted.empty:
        win_rate = (weighted["vs_fixed_dca"] > 0).mean()
        avg_edge = weighted["vs_fixed_dca"].mean()
        print(f"  Win rate: {win_rate:.1%} ({(weighted['vs_fixed_dca'] > 0).sum():,}/{len(weighted):,})")
        print(f"  Avg edge: {avg_edge:+.4f}")

        # By scheme
        print("\n  By scheme:")
        for scheme in ["linear", "threshold", "tiered", "inverse_sigmoid"]:
            sub = weighted[weighted["rsi_scheme"] == scheme]
            if sub.empty:
                continue
            wr = (sub["vs_fixed_dca"] > 0).mean()
            ae = sub["vs_fixed_dca"].mean()
            print(f"    {scheme:20s}: win {wr:.1%}, avg edge {ae:+.4f}")

    print(f"\nDone. Results: {out_path}")


if __name__ == "__main__":
    main()
