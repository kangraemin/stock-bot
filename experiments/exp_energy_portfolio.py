"""Experiment: Energy+Tech Cross-Sector Portfolio Backtest (~62,000 combinations)

Self-contained numpy-based portfolio backtester.
8 experiments: 2/3/4-asset portfolios, sector rotation, inverse-correlation hedge,
oil-based sector tilt, macro regime allocation, leveraged cross.
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

# ── Symbol Pools ──
ENERGY = ["CVX", "XOM", "XLE", "COP", "VDE", "ERX"]
TECH = ["QQQ", "NVDA", "TQQQ", "SOXX", "XLK", "AAPL"]
DEFENSE_ASSETS = ["GLD", "TLT", "BND", "XLP", "XLV", "SPY"]
LEV_ENERGY = ["ERX"]
LEV_TECH = ["TQQQ", "SOXL", "TECL"]

MACRO_SYMBOLS = ["CL=F", "^VIX", "^TNX"]

ALL_SYMBOLS = list(set(ENERGY + TECH + DEFENSE_ASSETS + LEV_TECH + MACRO_SYMBOLS))

# ── Rebalancing configs ──
REBAL_2A = [
    ("band", 0.03), ("band", 0.05), ("band", 0.10), ("band", 0.15),
    ("monthly", 0), ("quarterly", 0), ("annual", 0),
]
REBAL_3A = [
    ("band", 0.03), ("band", 0.05), ("band", 0.10), ("band", 0.15),
    ("monthly", 0), ("quarterly", 0), ("annual", 0),
]
REBAL_4A = [
    ("band", 0.05), ("band", 0.10), ("band", 0.15),
    ("monthly", 0), ("quarterly", 0), ("annual", 0),
]

# ── Weight configs ──
WEIGHT_2A = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]

WEIGHT_PRESETS_3 = [
    (0.40, 0.40, 0.20),
    (0.30, 0.30, 0.40),
    (0.50, 0.30, 0.20),
    (0.20, 0.20, 0.60),
    (0.30, 0.50, 0.20),
    (0.20, 0.50, 0.30),
    (0.15, 0.15, 0.70),
    (0.10, 0.30, 0.60),
    (0.40, 0.20, 0.40),
    (0.25, 0.25, 0.50),
]

WEIGHT_PRESETS_4 = [
    (0.25, 0.25, 0.25, 0.25),
    (0.30, 0.30, 0.20, 0.20),
    (0.15, 0.35, 0.30, 0.20),
    (0.20, 0.20, 0.40, 0.20),
    (0.10, 0.10, 0.40, 0.40),
]

# ── Experiment 4: Sector Rotation params ──
ROTATION_LOOKBACK = [21, 42, 63, 126, 252]
ROTATION_TOP_N = [1, 2, 3]
ROTATION_FREQ = [21, 42, 63]
ROTATION_MOM_TYPE = ["price", "risk_adj", "relative", "dual"]

# ── Experiment 5: Inverse-correlation hedge params ──
CORR_WIN = [21, 63, 126]
CORR_THRESH = [-0.3, -0.2, -0.1, 0.0]
HEDGE_RATIO = [0.2, 0.3, 0.5]
HEDGE_REBAL = [("monthly", 0), ("quarterly", 0), ("band", 0.05)]

# ── Experiment 6: Oil-based sector tilt params ──
OIL_MA = [20, 50, 100, 200]
E_WEIGHT_HIGH = [0.5, 0.6, 0.7, 0.8]
E_WEIGHT_LOW = [0.1, 0.2, 0.3]
OIL_REBAL = [("monthly", 0), ("quarterly", 0), ("band", 0.05), ("band", 0.10)]

# ── Experiment 7: Macro regime allocation params ──
REGIME_DEF = ["vix", "tnx", "composite"]
N_REGIMES = [2, 3]
REGIME_ALLOC_PRESETS = [
    {"risk_on": (0.6, 0.3, 0.1), "risk_off": (0.1, 0.3, 0.6)},
    {"risk_on": (0.5, 0.4, 0.1), "risk_off": (0.2, 0.2, 0.6)},
    {"risk_on": (0.7, 0.2, 0.1), "risk_off": (0.1, 0.2, 0.7)},
    {"risk_on": (0.4, 0.4, 0.2), "risk_off": (0.15, 0.25, 0.6)},
    {"risk_on": (0.5, 0.3, 0.2), "risk_off": (0.2, 0.3, 0.5)},
]
REGIME_REBAL = [("monthly", 0), ("quarterly", 0), ("band", 0.05), ("band", 0.10)]

# ── Global aligned data (populated in main, inherited by fork) ──
G_ALIGNED = []  # list of dicts with pre-split, pre-computed data
G_MACRO = {}    # macro data: {"CL=F": array, "^VIX": array, "^TNX": array, "dates": array}


# ═══════════════════════════════════════════════════════════════
# Portfolio simulation (same pattern as exp_portfolio_opt.py)
# ═══════════════════════════════════════════════════════════════

def simulate_portfolio(prices, weights, rebal_type, rebal_param, months, years):
    """
    prices: (n_days, n_assets) array
    weights: tuple/list of target weights
    rebal_type: "band" | "monthly" | "quarterly" | "semi_annual" | "annual"
    rebal_param: threshold for band, 0 for calendar
    months, years: int32 arrays for calendar rebalancing
    Returns: equity_curve, n_trades, n_rebal
    """
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
            cash = avail - sum(
                shares[j] * prices[i, j] * (1 + FEE_RATE) for j in range(n_assets)
            )
            total_trades += n_trades

    return equity, total_trades, rebal_count


def simulate_portfolio_dynamic(prices, weight_series, months, years):
    """
    Dynamic weight portfolio: weights change per day based on external signal.
    prices: (n_days, n_assets) array
    weight_series: (n_days, n_assets) array of target weights per day
    Returns: equity_curve, n_trades, n_rebal
    """
    n_days, n_assets = prices.shape
    equity = np.empty(n_days, dtype=np.float64)

    target_w = weight_series[0]
    shares = np.zeros(n_assets, dtype=np.float64)
    cash = CAPITAL
    for j in range(n_assets):
        alloc = CAPITAL * target_w[j]
        if prices[0, j] > 0:
            shares[j] = alloc / (prices[0, j] * (1 + FEE_RATE))
            cash -= shares[j] * prices[0, j] * (1 + FEE_RATE)

    total_trades = n_assets
    rebal_count = 0
    prev_w = target_w.copy()

    for i in range(n_days):
        asset_values = shares * prices[i]
        total_eq = np.sum(asset_values) + cash
        equity[i] = total_eq

        if i == 0:
            continue
        if total_eq <= 0:
            equity[i:] = 0
            break

        new_w = weight_series[i]
        if not np.allclose(new_w, prev_w, atol=0.01):
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
                if prices[i, j] > 0 and new_w[j] > 0:
                    shares[j] = (avail * new_w[j]) / (prices[i, j] * (1 + FEE_RATE))
                    n_trades += 1
            cash = avail - sum(
                shares[j] * prices[i, j] * (1 + FEE_RATE) for j in range(n_assets)
            )
            total_trades += n_trades
            prev_w = new_w.copy()

    return equity, total_trades, rebal_count


def compute_bh_return(prices, weights):
    n_assets = prices.shape[1]
    tw = np.array(weights, dtype=np.float64)
    shares = np.zeros(n_assets)
    for j in range(n_assets):
        shares[j] = (CAPITAL * tw[j]) / (prices[0, j] * (1 + FEE_RATE))
    cash = CAPITAL - sum(
        shares[j] * prices[0, j] * (1 + FEE_RATE) for j in range(n_assets)
    )
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


# ═══════════════════════════════════════════════════════════════
# Data alignment
# ═══════════════════════════════════════════════════════════════

def align_prices(all_close, symbols):
    """Align multiple symbols to common dates.
    Returns: prices (n_days, n_assets), dates array, or None if insufficient overlap.
    """
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
    return prices, dates


def split_is_oos(prices, dates):
    """Split into IS/OOS. Returns dict or None."""
    split = int(len(dates) * IS_RATIO)
    if split < 100 or (len(dates) - split) < 50:
        return None
    is_pd = pd.DatetimeIndex(dates[:split])
    oos_pd = pd.DatetimeIndex(dates[split:])
    return {
        "is_d": dates[:split], "oos_d": dates[split:],
        "is_prices": prices[:split].astype(np.float64),
        "oos_prices": prices[split:].astype(np.float64),
        "is_m": is_pd.month.values.astype(np.int32),
        "is_y": is_pd.year.values.astype(np.int32),
        "oos_m": oos_pd.month.values.astype(np.int32),
        "oos_y": oos_pd.year.values.astype(np.int32),
    }


# ═══════════════════════════════════════════════════════════════
# Worker functions
# ═══════════════════════════════════════════════════════════════

def _make_result(symbols, weights, rtype, rparam, experiment, is_met, oos_met, bh):
    rl = f"band_{int(rparam*100)}%" if rtype == "band" else rtype
    return {
        "assets": "|".join(symbols),
        "n_assets": len(symbols),
        "weights": "|".join(f"{w:.3f}" for w in weights),
        "rebal_label": rl,
        "experiment": experiment,
        "is_return": round(is_met["total_return"], 4),
        "is_sharpe": round(is_met["sharpe"], 4),
        "is_maxdd": round(is_met["maxdd"], 4),
        "is_trades": is_met["trades"],
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
    }


def _worker_static_batch(batch):
    """Process static portfolio batch.
    Each item: (symbols, weights, rtype, rparam, experiment, aidx, col_indices)
    """
    results = []
    for symbols, weights, rtype, rparam, experiment, aidx, col_idx in batch:
        ad = G_ALIGNED[aidx]
        is_p = ad["is_prices"][:, col_idx]
        oos_p = ad["oos_prices"][:, col_idx]

        is_eq, is_tr, is_rb = simulate_portfolio(
            is_p, weights, rtype, rparam, ad["is_m"], ad["is_y"]
        )
        is_met = compute_metrics(is_eq, ad["is_d"], is_tr, is_rb)
        if is_met is None:
            continue

        oos_eq, oos_tr, oos_rb = simulate_portfolio(
            oos_p, weights, rtype, rparam, ad["oos_m"], ad["oos_y"]
        )
        oos_met = compute_metrics(oos_eq, ad["oos_d"], oos_tr, oos_rb)
        if oos_met is None:
            continue

        bh = compute_bh_return(oos_p, weights)
        results.append(_make_result(symbols, weights, rtype, rparam, experiment, is_met, oos_met, bh))
    return results


def _worker_rotation_batch(batch):
    """Process sector rotation batch.
    Each item: (lookback, top_n, freq, mom_type, aidx)
    """
    results = []
    for lookback, top_n, freq, mom_type, aidx in batch:
        ad = G_ALIGNED[aidx]
        symbols = ad["sym_order"]
        n_assets = len(symbols)

        for phase_key, prices, dates, months, years in [
            ("is", ad["is_prices"], ad["is_d"], ad["is_m"], ad["is_y"]),
            ("oos", ad["oos_prices"], ad["oos_d"], ad["oos_m"], ad["oos_y"]),
        ]:
            n_days = prices.shape[0]
            if n_days < lookback + freq:
                break

            equity = np.empty(n_days, dtype=np.float64)
            shares = np.zeros(n_assets, dtype=np.float64)
            cash = CAPITAL
            total_trades = 0
            rebal_count = 0
            last_rebal = -freq  # force initial allocation

            for i in range(n_days):
                asset_values = shares * prices[i]
                total_eq = np.sum(asset_values) + cash
                equity[i] = total_eq

                if total_eq <= 0:
                    equity[i:] = 0
                    break

                if i - last_rebal >= freq and i >= lookback:
                    # Compute momentum
                    ret_window = prices[i] / prices[i - lookback] - 1.0

                    if mom_type == "price":
                        scores = ret_window
                    elif mom_type == "risk_adj":
                        stds = np.std(np.diff(prices[i-lookback:i+1], axis=0) /
                                      prices[i-lookback:i, :], axis=0, ddof=1)
                        scores = np.where(stds > 0, ret_window / stds, 0.0)
                    elif mom_type == "relative":
                        avg = np.mean(ret_window)
                        scores = ret_window - avg
                    elif mom_type == "dual":
                        # Positive absolute + relative
                        avg = np.mean(ret_window)
                        scores = np.where(ret_window > 0, ret_window - avg, -1e6)
                    else:
                        scores = ret_window

                    top_idx = np.argsort(scores)[-top_n:]
                    target_w = np.zeros(n_assets)
                    for idx in top_idx:
                        target_w[idx] = 1.0 / top_n

                    # Rebalance
                    sell_rev = 0.0
                    n_tr = 0
                    for j in range(n_assets):
                        if shares[j] > 0:
                            sell_rev += shares[j] * prices[i, j] * (1 - FEE_RATE)
                            n_tr += 1
                            shares[j] = 0.0
                    avail = cash + sell_rev
                    for j in range(n_assets):
                        if target_w[j] > 0 and prices[i, j] > 0:
                            shares[j] = (avail * target_w[j]) / (prices[i, j] * (1 + FEE_RATE))
                            n_tr += 1
                    cash = avail - sum(
                        shares[j] * prices[i, j] * (1 + FEE_RATE) for j in range(n_assets)
                    )
                    total_trades += n_tr
                    rebal_count += 1
                    last_rebal = i

            if phase_key == "is":
                is_met = compute_metrics(equity, dates, total_trades, rebal_count)
                if is_met is None:
                    break
                is_met_saved = is_met
            else:
                oos_met = compute_metrics(equity, dates, total_trades, rebal_count)
                if oos_met is None:
                    break

                # B&H equal weight
                bh = compute_bh_return(prices, [1.0/n_assets]*n_assets)
                rl = f"rot_{freq}d"
                results.append({
                    "assets": "|".join(symbols),
                    "n_assets": n_assets,
                    "weights": f"top{top_n}|lb{lookback}|{mom_type}",
                    "rebal_label": rl,
                    "experiment": "4_rotation",
                    "is_return": round(is_met_saved["total_return"], 4),
                    "is_sharpe": round(is_met_saved["sharpe"], 4),
                    "is_maxdd": round(is_met_saved["maxdd"], 4),
                    "is_trades": is_met_saved["trades"],
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
                })
    return results


def _worker_corr_hedge_batch(batch):
    """Process inverse-correlation hedge batch.
    Each item: (energy_sym, tech_sym, defense_sym, corr_win, corr_thresh,
                hedge_ratio, rtype, rparam, aidx)
    """
    results = []
    for (energy_sym, tech_sym, defense_sym, corr_win, corr_thresh,
         hedge_ratio, rtype, rparam, aidx) in batch:
        ad = G_ALIGNED[aidx]
        symbols = ad["sym_order"]
        col_e = symbols.index(energy_sym)
        col_t = symbols.index(tech_sym)
        col_d = symbols.index(defense_sym)

        for phase_key, prices, dates, months, years in [
            ("is", ad["is_prices"], ad["is_d"], ad["is_m"], ad["is_y"]),
            ("oos", ad["oos_prices"], ad["oos_d"], ad["oos_m"], ad["oos_y"]),
        ]:
            n_days = prices.shape[0]
            if n_days < corr_win + 10:
                break

            # Compute rolling correlation between energy and tech
            ret_e = np.diff(prices[:, col_e]) / prices[:-1, col_e]
            ret_t = np.diff(prices[:, col_t]) / prices[:-1, col_t]

            # Build dynamic weight series (n_days, 3)
            weight_series = np.zeros((n_days, 3), dtype=np.float64)
            base_e = (1.0 - hedge_ratio) * 0.5
            base_t = (1.0 - hedge_ratio) * 0.5
            base_d = hedge_ratio
            weight_series[:, 0] = base_e
            weight_series[:, 1] = base_t
            weight_series[:, 2] = base_d

            for i in range(corr_win, n_days - 1):
                win_e = ret_e[i-corr_win:i]
                win_t = ret_t[i-corr_win:i]
                if np.std(win_e) > 0 and np.std(win_t) > 0:
                    corr = np.corrcoef(win_e, win_t)[0, 1]
                else:
                    corr = 0.0

                if corr < corr_thresh:
                    # Negative correlation: increase hedge
                    weight_series[i+1, 0] = base_e * 0.7
                    weight_series[i+1, 1] = base_t * 0.7
                    weight_series[i+1, 2] = 1.0 - weight_series[i+1, 0] - weight_series[i+1, 1]
                else:
                    weight_series[i+1, 0] = base_e
                    weight_series[i+1, 1] = base_t
                    weight_series[i+1, 2] = base_d

            # Use static rebalancing with the average weights for simplicity
            col_idx = [col_e, col_t, col_d]
            p3 = prices[:, col_idx]
            avg_w = (base_e, base_t, base_d)

            eq, tr, rb = simulate_portfolio(p3, avg_w, rtype, rparam, months, years)
            met = compute_metrics(eq, dates, tr, rb)
            if met is None:
                break

            if phase_key == "is":
                is_met_saved = met
            else:
                bh = compute_bh_return(p3, avg_w)
                rl = f"band_{int(rparam*100)}%" if rtype == "band" else rtype
                results.append({
                    "assets": f"{energy_sym}|{tech_sym}|{defense_sym}",
                    "n_assets": 3,
                    "weights": f"{base_e:.3f}|{base_t:.3f}|{base_d:.3f}|cw{corr_win}|ct{corr_thresh}",
                    "rebal_label": rl,
                    "experiment": "5_corr_hedge",
                    "is_return": round(is_met_saved["total_return"], 4),
                    "is_sharpe": round(is_met_saved["sharpe"], 4),
                    "is_maxdd": round(is_met_saved["maxdd"], 4),
                    "is_trades": is_met_saved["trades"],
                    "oos_return": round(met["total_return"], 4),
                    "oos_sharpe": round(met["sharpe"], 4),
                    "oos_maxdd": round(met["maxdd"], 4),
                    "oos_calmar": round(met["calmar"], 4),
                    "oos_trades": met["trades"],
                    "oos_rebal_count": met["rebal_count"],
                    "bh_return": round(bh, 4),
                    "vs_bh": round(met["total_return"] - bh, 4),
                    "years": met["years"],
                    "trades_per_year": met["trades_per_year"],
                })
    return results


def _worker_oil_tilt_batch(batch):
    """Process oil-based sector tilt batch.
    Each item: (energy_sym, tech_sym, oil_ma, e_w_high, e_w_low, rtype, rparam, aidx)
    """
    results = []
    for energy_sym, tech_sym, oil_ma, e_w_high, e_w_low, rtype, rparam, aidx in batch:
        ad = G_ALIGNED[aidx]
        symbols = ad["sym_order"]
        col_e = symbols.index(energy_sym)
        col_t = symbols.index(tech_sym)

        # Get oil data aligned to portfolio dates
        oil_dates = G_MACRO.get("dates")
        oil_prices = G_MACRO.get("CL=F")
        if oil_dates is None or oil_prices is None:
            continue

        for phase_key, prices, dates, months, years in [
            ("is", ad["is_prices"], ad["is_d"], ad["is_m"], ad["is_y"]),
            ("oos", ad["oos_prices"], ad["oos_d"], ad["oos_m"], ad["oos_y"]),
        ]:
            n_days = prices.shape[0]
            if n_days < oil_ma + 10:
                break

            # Align oil to portfolio dates
            oil_aligned = np.full(n_days, np.nan)
            oil_date_set = {d: idx for idx, d in enumerate(oil_dates)}
            for i, d in enumerate(dates):
                if d in oil_date_set:
                    oil_aligned[i] = oil_prices[oil_date_set[d]]

            # Forward fill NaN
            for i in range(1, n_days):
                if np.isnan(oil_aligned[i]):
                    oil_aligned[i] = oil_aligned[i-1]

            # Build dynamic weight series
            weight_series = np.zeros((n_days, 2), dtype=np.float64)
            weight_series[:, 0] = 0.5  # default
            weight_series[:, 1] = 0.5

            for i in range(oil_ma, n_days):
                oil_sma = np.nanmean(oil_aligned[i-oil_ma:i])
                if not np.isnan(oil_aligned[i]) and not np.isnan(oil_sma):
                    if oil_aligned[i] > oil_sma:
                        weight_series[i, 0] = e_w_high
                        weight_series[i, 1] = 1.0 - e_w_high
                    else:
                        weight_series[i, 0] = e_w_low
                        weight_series[i, 1] = 1.0 - e_w_low

            # Simulate with calendar/band rebalancing using average effective weights
            col_idx = [col_e, col_t]
            p2 = prices[:, col_idx]

            # Use dynamic simulation
            eq, tr, rb = simulate_portfolio_dynamic(p2, weight_series, months, years)
            met = compute_metrics(eq, dates, tr, rb)
            if met is None:
                break

            if phase_key == "is":
                is_met_saved = met
            else:
                bh = compute_bh_return(p2, [0.5, 0.5])
                rl = f"band_{int(rparam*100)}%" if rtype == "band" else rtype
                results.append({
                    "assets": f"{energy_sym}|{tech_sym}",
                    "n_assets": 2,
                    "weights": f"oil_ma{oil_ma}|high{e_w_high}|low{e_w_low}",
                    "rebal_label": rl,
                    "experiment": "6_oil_tilt",
                    "is_return": round(is_met_saved["total_return"], 4),
                    "is_sharpe": round(is_met_saved["sharpe"], 4),
                    "is_maxdd": round(is_met_saved["maxdd"], 4),
                    "is_trades": is_met_saved["trades"],
                    "oos_return": round(met["total_return"], 4),
                    "oos_sharpe": round(met["sharpe"], 4),
                    "oos_maxdd": round(met["maxdd"], 4),
                    "oos_calmar": round(met["calmar"], 4),
                    "oos_trades": met["trades"],
                    "oos_rebal_count": met["rebal_count"],
                    "bh_return": round(bh, 4),
                    "vs_bh": round(met["total_return"] - bh, 4),
                    "years": met["years"],
                    "trades_per_year": met["trades_per_year"],
                })
    return results


def _worker_regime_batch(batch):
    """Process macro regime allocation batch.
    Each item: (energy_sym, tech_sym, defense_sym, regime_def, n_regimes,
                alloc_preset_idx, rtype, rparam, aidx)
    """
    results = []
    for (energy_sym, tech_sym, defense_sym, regime_def, n_regimes,
         alloc_idx, rtype, rparam, aidx) in batch:
        ad = G_ALIGNED[aidx]
        symbols = ad["sym_order"]
        col_e = symbols.index(energy_sym)
        col_t = symbols.index(tech_sym)
        col_d = symbols.index(defense_sym)
        alloc_preset = REGIME_ALLOC_PRESETS[alloc_idx]

        for phase_key, prices, dates, months, years in [
            ("is", ad["is_prices"], ad["is_d"], ad["is_m"], ad["is_y"]),
            ("oos", ad["oos_prices"], ad["oos_d"], ad["oos_m"], ad["oos_y"]),
        ]:
            n_days = prices.shape[0]

            # Get macro signal aligned to dates
            if regime_def == "vix":
                macro_key = "^VIX"
            elif regime_def == "tnx":
                macro_key = "^TNX"
            else:
                macro_key = None  # composite

            macro_dates = G_MACRO.get("dates")
            if macro_dates is None:
                break

            # Determine regime per day
            regime_signal = np.zeros(n_days, dtype=np.float64)

            if macro_key is not None:
                macro_vals = G_MACRO.get(macro_key)
                if macro_vals is None:
                    break
                macro_date_set = {d: idx for idx, d in enumerate(macro_dates)}
                for i, d in enumerate(dates):
                    if d in macro_date_set:
                        regime_signal[i] = macro_vals[macro_date_set[d]]
                    elif i > 0:
                        regime_signal[i] = regime_signal[i-1]
            else:
                # Composite: VIX + TNX
                vix_vals = G_MACRO.get("^VIX")
                tnx_vals = G_MACRO.get("^TNX")
                if vix_vals is None or tnx_vals is None:
                    break
                macro_date_set = {d: idx for idx, d in enumerate(macro_dates)}
                vix_aligned = np.zeros(n_days)
                tnx_aligned = np.zeros(n_days)
                for i, d in enumerate(dates):
                    if d in macro_date_set:
                        vix_aligned[i] = vix_vals[macro_date_set[d]]
                        tnx_aligned[i] = tnx_vals[macro_date_set[d]]
                    elif i > 0:
                        vix_aligned[i] = vix_aligned[i-1]
                        tnx_aligned[i] = tnx_aligned[i-1]
                # Normalize and combine
                if np.std(vix_aligned) > 0:
                    vix_z = (vix_aligned - np.mean(vix_aligned)) / np.std(vix_aligned)
                else:
                    vix_z = np.zeros(n_days)
                if np.std(tnx_aligned) > 0:
                    tnx_z = (tnx_aligned - np.mean(tnx_aligned)) / np.std(tnx_aligned)
                else:
                    tnx_z = np.zeros(n_days)
                regime_signal = vix_z + tnx_z  # higher = more stress

            # Classify into regimes using percentiles
            if n_regimes == 2:
                median_val = np.median(regime_signal)
                regimes = np.where(regime_signal <= median_val, 0, 1)  # 0=risk_on, 1=risk_off
            else:
                p33 = np.percentile(regime_signal, 33)
                p66 = np.percentile(regime_signal, 66)
                regimes = np.where(regime_signal <= p33, 0,
                           np.where(regime_signal <= p66, 1, 2))

            # Build weight series
            w_on = np.array(alloc_preset["risk_on"], dtype=np.float64)
            w_off = np.array(alloc_preset["risk_off"], dtype=np.float64)
            if n_regimes == 3:
                w_mid = (w_on + w_off) / 2.0
            weight_series = np.zeros((n_days, 3), dtype=np.float64)
            for i in range(n_days):
                if regimes[i] == 0:
                    weight_series[i] = w_on
                elif n_regimes == 2:
                    weight_series[i] = w_off
                elif regimes[i] == 1:
                    weight_series[i] = w_mid
                else:
                    weight_series[i] = w_off

            col_idx = [col_e, col_t, col_d]
            p3 = prices[:, col_idx]

            eq, tr, rb = simulate_portfolio_dynamic(p3, weight_series, months, years)
            met = compute_metrics(eq, dates, tr, rb)
            if met is None:
                break

            if phase_key == "is":
                is_met_saved = met
            else:
                bh = compute_bh_return(p3, [1/3, 1/3, 1/3])
                rl = f"band_{int(rparam*100)}%" if rtype == "band" else rtype
                results.append({
                    "assets": f"{energy_sym}|{tech_sym}|{defense_sym}",
                    "n_assets": 3,
                    "weights": f"regime_{regime_def}|n{n_regimes}|preset{alloc_idx}",
                    "rebal_label": rl,
                    "experiment": "7_macro_regime",
                    "is_return": round(is_met_saved["total_return"], 4),
                    "is_sharpe": round(is_met_saved["sharpe"], 4),
                    "is_maxdd": round(is_met_saved["maxdd"], 4),
                    "is_trades": is_met_saved["trades"],
                    "oos_return": round(met["total_return"], 4),
                    "oos_sharpe": round(met["sharpe"], 4),
                    "oos_maxdd": round(met["maxdd"], 4),
                    "oos_calmar": round(met["calmar"], 4),
                    "oos_trades": met["trades"],
                    "oos_rebal_count": met["rebal_count"],
                    "bh_return": round(bh, 4),
                    "vs_bh": round(met["total_return"] - bh, 4),
                    "years": met["years"],
                    "trades_per_year": met["trades_per_year"],
                })
    return results


# ═══════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════

def main():
    global G_ALIGNED, G_MACRO

    t0 = time.time()

    # ── Load all data ──
    print("Loading data...")
    all_close = {}
    for sym in ALL_SYMBOLS:
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

    # ── Load macro data ──
    print("Loading macro data...")
    macro_series = {}
    for sym in MACRO_SYMBOLS:
        if sym in all_close:
            macro_series[sym] = all_close[sym]
            print(f"  {sym}: {len(all_close[sym])} days")
        else:
            print(f"  {sym}: MISSING")

    if macro_series:
        # Align macro data to common dates
        common_idx = None
        for sym, s in macro_series.items():
            if common_idx is None:
                common_idx = s.index
            else:
                common_idx = common_idx.intersection(s.index)
        if common_idx is not None and len(common_idx) > 100:
            common_idx = common_idx.sort_values()
            G_MACRO["dates"] = common_idx.values.astype("datetime64[D]")
            for sym, s in macro_series.items():
                G_MACRO[sym] = s.loc[common_idx].values.astype(np.float64)
            print(f"  Macro aligned: {len(common_idx)} days")
    print()

    # ── Pre-compute aligned datasets for all unique symbol combinations ──
    print("Pre-computing aligned data...")
    asset_sets = set()

    # Exp 1: Energy x Tech pairs
    for e in ENERGY:
        for t in TECH:
            asset_sets.add(tuple(sorted([e, t])))

    # Exp 2: Energy x Tech x Defense triples
    for e in ENERGY:
        for t in TECH:
            for d in DEFENSE_ASSETS:
                asset_sets.add(tuple(sorted([e, t, d])))

    # Exp 3: Energy x Tech x Defense x Alpha quads (use DEFENSE as alpha too)
    for e in ENERGY:
        for t in TECH:
            for d1, d2 in itertools.combinations(DEFENSE_ASSETS, 2):
                asset_sets.add(tuple(sorted([e, t, d1, d2])))

    # Exp 4: Rotation pool (all energy + tech combined)
    rotation_pool = tuple(sorted(set(ENERGY + TECH)))
    asset_sets.add(rotation_pool)

    # Exp 5: Corr hedge triples (same as exp 2 subset)
    # Already covered above

    # Exp 8: Leveraged cross
    for lev_e in LEV_ENERGY:
        for lev_t in LEV_TECH:
            asset_sets.add(tuple(sorted([lev_e, lev_t])))
            for d in DEFENSE_ASSETS:
                asset_sets.add(tuple(sorted([lev_e, lev_t, d])))

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
            "sym_order": list(akey),
        })

    print(f"  Valid: {len(G_ALIGNED):,}, Skipped: {skipped}")
    del all_close
    print(f"  Aligned data ready ({time.time()-t0:.1f}s)\n")

    # ═══════════════════════════════════════════════════════════
    # Generate all combinations
    # ═══════════════════════════════════════════════════════════
    print("Generating combinations...")

    static_combos = []   # for _worker_static_batch
    rotation_combos = [] # for _worker_rotation_batch
    corr_combos = []     # for _worker_corr_hedge_batch
    oil_combos = []      # for _worker_oil_tilt_batch
    regime_combos = []   # for _worker_regime_batch

    n1 = n2 = n3 = n4 = n5 = n6 = n7 = n8 = 0

    # ── Exp 1: Energy+Tech 2-asset ──
    for e_sym in ENERGY:
        for t_sym in TECH:
            akey = tuple(sorted([e_sym, t_sym]))
            if akey not in akey_to_idx:
                continue
            aidx = akey_to_idx[akey]
            sym_order = G_ALIGNED[aidx]["sym_order"]
            col_idx = [sym_order.index(e_sym), sym_order.index(t_sym)]
            for e_w in WEIGHT_2A:
                for rt, rp in REBAL_2A:
                    static_combos.append(
                        ([e_sym, t_sym], (e_w, 1-e_w), rt, rp, "1_energy_tech_2a", aidx, col_idx)
                    )
                    n1 += 1

    # ── Exp 2: Energy+Tech+Defense 3-asset ──
    for e_sym in ENERGY:
        for t_sym in TECH:
            for d_sym in DEFENSE_ASSETS:
                akey = tuple(sorted([e_sym, t_sym, d_sym]))
                if akey not in akey_to_idx:
                    continue
                aidx = akey_to_idx[akey]
                sym_order = G_ALIGNED[aidx]["sym_order"]
                col_idx = [sym_order.index(e_sym), sym_order.index(t_sym), sym_order.index(d_sym)]
                for w in WEIGHT_PRESETS_3:
                    for rt, rp in REBAL_3A:
                        static_combos.append(
                            ([e_sym, t_sym, d_sym], w, rt, rp, "2_energy_tech_def_3a", aidx, col_idx)
                        )
                        n2 += 1

    # ── Exp 3: Energy+Tech+Defense+Alpha 4-asset ──
    for e_sym in ENERGY:
        for t_sym in TECH:
            for d1, d2 in itertools.combinations(DEFENSE_ASSETS, 2):
                akey = tuple(sorted([e_sym, t_sym, d1, d2]))
                if akey not in akey_to_idx:
                    continue
                aidx = akey_to_idx[akey]
                sym_order = G_ALIGNED[aidx]["sym_order"]
                col_idx = [sym_order.index(e_sym), sym_order.index(t_sym),
                           sym_order.index(d1), sym_order.index(d2)]
                for w in WEIGHT_PRESETS_4:
                    for rt, rp in REBAL_4A:
                        static_combos.append(
                            ([e_sym, t_sym, d1, d2], w, rt, rp, "3_4asset", aidx, col_idx)
                        )
                        n3 += 1

    # ── Exp 4: Sector Rotation ──
    rotation_pool_key = tuple(sorted(set(ENERGY + TECH)))
    if rotation_pool_key in akey_to_idx:
        rot_aidx = akey_to_idx[rotation_pool_key]
        for lb in ROTATION_LOOKBACK:
            for tn in ROTATION_TOP_N:
                for freq in ROTATION_FREQ:
                    for mt in ROTATION_MOM_TYPE:
                        rotation_combos.append((lb, tn, freq, mt, rot_aidx))
                        n4 += 1

    # ── Exp 5: Inverse-correlation hedge ──
    for e_sym in ENERGY[:3]:  # subset to limit combos
        for t_sym in TECH[:3]:
            for d_sym in DEFENSE_ASSETS[:3]:
                akey = tuple(sorted([e_sym, t_sym, d_sym]))
                if akey not in akey_to_idx:
                    continue
                aidx = akey_to_idx[akey]
                for cw in CORR_WIN:
                    for ct in CORR_THRESH:
                        for hr in HEDGE_RATIO:
                            for rt, rp in HEDGE_REBAL:
                                corr_combos.append(
                                    (e_sym, t_sym, d_sym, cw, ct, hr, rt, rp, aidx)
                                )
                                n5 += 1

    # ── Exp 6: Oil-based sector tilt ──
    for e_sym in ENERGY:
        for t_sym in TECH:
            akey = tuple(sorted([e_sym, t_sym]))
            if akey not in akey_to_idx:
                continue
            aidx = akey_to_idx[akey]
            for oma in OIL_MA:
                for ewh in E_WEIGHT_HIGH:
                    for ewl in E_WEIGHT_LOW:
                        for rt, rp in OIL_REBAL:
                            oil_combos.append(
                                (e_sym, t_sym, oma, ewh, ewl, rt, rp, aidx)
                            )
                            n6 += 1

    # ── Exp 7: Macro regime allocation ──
    for e_sym in ENERGY[:3]:
        for t_sym in TECH[:3]:
            for d_sym in DEFENSE_ASSETS[:3]:
                akey = tuple(sorted([e_sym, t_sym, d_sym]))
                if akey not in akey_to_idx:
                    continue
                aidx = akey_to_idx[akey]
                for rd in REGIME_DEF:
                    for nr in N_REGIMES:
                        for ai in range(len(REGIME_ALLOC_PRESETS)):
                            for rt, rp in REGIME_REBAL:
                                regime_combos.append(
                                    (e_sym, t_sym, d_sym, rd, nr, ai, rt, rp, aidx)
                                )
                                n7 += 1

    # ── Exp 8: Leveraged cross ──
    for lev_e in LEV_ENERGY:
        # 2-asset: ERX vs lev tech
        for lev_t in LEV_TECH:
            akey = tuple(sorted([lev_e, lev_t]))
            if akey not in akey_to_idx:
                continue
            aidx = akey_to_idx[akey]
            sym_order = G_ALIGNED[aidx]["sym_order"]
            col_idx = [sym_order.index(lev_e), sym_order.index(lev_t)]
            for e_w in WEIGHT_2A:
                for rt, rp in REBAL_2A:
                    static_combos.append(
                        ([lev_e, lev_t], (e_w, 1-e_w), rt, rp, "8_lev_cross_2a", aidx, col_idx)
                    )
                    n8 += 1

        # 3-asset: ERX + lev tech + defense
        for lev_t in LEV_TECH:
            for d_sym in DEFENSE_ASSETS:
                akey = tuple(sorted([lev_e, lev_t, d_sym]))
                if akey not in akey_to_idx:
                    continue
                aidx = akey_to_idx[akey]
                sym_order = G_ALIGNED[aidx]["sym_order"]
                col_idx = [sym_order.index(lev_e), sym_order.index(lev_t), sym_order.index(d_sym)]
                for w in WEIGHT_PRESETS_3:
                    for rt, rp in REBAL_3A[:5]:  # reduce combos
                        static_combos.append(
                            ([lev_e, lev_t, d_sym], w, rt, rp, "8_lev_cross_3a", aidx, col_idx)
                        )
                        n8 += 1

    total_combos = len(static_combos) + len(rotation_combos) + len(corr_combos) + len(oil_combos) + len(regime_combos)

    print(f"  Exp 1 (Energy+Tech 2a):        {n1:,}")
    print(f"  Exp 2 (E+T+Def 3a):            {n2:,}")
    print(f"  Exp 3 (4-asset):               {n3:,}")
    print(f"  Exp 4 (Sector Rotation):       {n4:,}")
    print(f"  Exp 5 (Corr Hedge):            {n5:,}")
    print(f"  Exp 6 (Oil Tilt):              {n6:,}")
    print(f"  Exp 7 (Macro Regime):          {n7:,}")
    print(f"  Exp 8 (Leveraged Cross):       {n8:,}")
    print(f"  Total:                         {total_combos:,}\n")

    # ═══════════════════════════════════════════════════════════
    # Run with fork-based multiprocessing
    # ═══════════════════════════════════════════════════════════
    batch_size = 500
    n_workers = max(1, mp.cpu_count() - 1)
    print(f"Processing with {n_workers} workers (fork)...")
    sys.stdout.flush()

    all_results = []
    ctx = mp.get_context("fork")

    # ── Static portfolios (Exp 1, 2, 3, 8) ──
    if static_combos:
        batches = [static_combos[i:i+batch_size] for i in range(0, len(static_combos), batch_size)]
        print(f"  Static portfolios: {len(static_combos):,} combos, {len(batches)} batches")
        sys.stdout.flush()
        processed = 0
        with ctx.Pool(n_workers) as pool:
            for batch_result in pool.imap_unordered(_worker_static_batch, batches):
                all_results.extend(batch_result)
                processed += batch_size
                if processed % 10000 < batch_size:
                    elapsed = time.time() - t0
                    rate = processed / elapsed if elapsed > 0 else 0
                    print(f"    Progress: {processed:,}/{len(static_combos):,} "
                          f"({processed/len(static_combos)*100:.1f}%) "
                          f"| {rate:.0f}/s | results: {len(all_results):,}")
                    sys.stdout.flush()
        print(f"  Static done: {len(all_results):,} results")

    # ── Sector Rotation (Exp 4) ──
    if rotation_combos:
        batches = [rotation_combos[i:i+50] for i in range(0, len(rotation_combos), 50)]
        print(f"  Rotation: {len(rotation_combos):,} combos, {len(batches)} batches")
        sys.stdout.flush()
        n_before = len(all_results)
        with ctx.Pool(n_workers) as pool:
            for batch_result in pool.imap_unordered(_worker_rotation_batch, batches):
                all_results.extend(batch_result)
        print(f"  Rotation done: {len(all_results) - n_before:,} results")

    # ── Correlation Hedge (Exp 5) ──
    if corr_combos:
        batches = [corr_combos[i:i+100] for i in range(0, len(corr_combos), 100)]
        print(f"  Corr Hedge: {len(corr_combos):,} combos, {len(batches)} batches")
        sys.stdout.flush()
        n_before = len(all_results)
        with ctx.Pool(n_workers) as pool:
            for batch_result in pool.imap_unordered(_worker_corr_hedge_batch, batches):
                all_results.extend(batch_result)
        print(f"  Corr Hedge done: {len(all_results) - n_before:,} results")

    # ── Oil Tilt (Exp 6) ──
    if oil_combos:
        batches = [oil_combos[i:i+100] for i in range(0, len(oil_combos), 100)]
        print(f"  Oil Tilt: {len(oil_combos):,} combos, {len(batches)} batches")
        sys.stdout.flush()
        n_before = len(all_results)
        with ctx.Pool(n_workers) as pool:
            for batch_result in pool.imap_unordered(_worker_oil_tilt_batch, batches):
                all_results.extend(batch_result)
        print(f"  Oil Tilt done: {len(all_results) - n_before:,} results")

    # ── Macro Regime (Exp 7) ──
    if regime_combos:
        batches = [regime_combos[i:i+100] for i in range(0, len(regime_combos), 100)]
        print(f"  Macro Regime: {len(regime_combos):,} combos, {len(batches)} batches")
        sys.stdout.flush()
        n_before = len(all_results)
        with ctx.Pool(n_workers) as pool:
            for batch_result in pool.imap_unordered(_worker_regime_batch, batches):
                all_results.extend(batch_result)
        print(f"  Macro Regime done: {len(all_results) - n_before:,} results")

    elapsed = time.time() - t0
    print(f"\nDone! {len(all_results):,} valid results in {elapsed:.1f}s "
          f"({total_combos/elapsed:.0f} combos/sec)\n")

    # ═══════════════════════════════════════════════════════════
    # Save results
    # ═══════════════════════════════════════════════════════════
    df = pd.DataFrame(all_results)
    csv_path = RESULTS_DIR / "energy_portfolio_results.csv"
    df.to_csv(csv_path, index=False)
    print(f"Saved to {csv_path}\n")

    if df.empty:
        print("No valid results.")
        return

    # ═══════════════════════════════════════════════════════════
    # Summaries
    # ═══════════════════════════════════════════════════════════
    cols = ["assets", "weights", "rebal_label", "experiment",
            "oos_return", "oos_sharpe", "oos_maxdd", "oos_calmar",
            "oos_trades", "oos_rebal_count",
            "bh_return", "vs_bh", "years", "trades_per_year"]

    exp_labels = {
        "1_energy_tech_2a": "EXP 1: ENERGY+TECH 2-ASSET",
        "2_energy_tech_def_3a": "EXP 2: ENERGY+TECH+DEFENSE 3-ASSET",
        "3_4asset": "EXP 3: 4-ASSET",
        "4_rotation": "EXP 4: SECTOR ROTATION",
        "5_corr_hedge": "EXP 5: CORRELATION HEDGE",
        "6_oil_tilt": "EXP 6: OIL-BASED SECTOR TILT",
        "7_macro_regime": "EXP 7: MACRO REGIME ALLOCATION",
        "8_lev_cross_2a": "EXP 8: LEVERAGED CROSS (2A)",
        "8_lev_cross_3a": "EXP 8: LEVERAGED CROSS (3A)",
    }

    for exp_key, label in exp_labels.items():
        sub = df[df["experiment"] == exp_key]
        if sub.empty:
            continue
        print("=" * 140)
        print(f"TOP 20 BY OOS SHARPE - {label} ({len(sub):,} combos)")
        print("=" * 140)
        top = sub.nlargest(20, "oos_sharpe")
        print(top[cols].to_string(index=False))
        print()

    # ── Overall Top 20 by OOS Sharpe ──
    print("=" * 140)
    print(f"TOP 20 BY OOS SHARPE - ALL EXPERIMENTS ({len(df):,} total)")
    print("=" * 140)
    print(df.nlargest(20, "oos_sharpe")[cols].to_string(index=False))
    print()

    # ── Overall Top 20 by OOS Calmar ──
    print("=" * 140)
    print("TOP 20 BY OOS CALMAR RATIO (ALL)")
    print("=" * 140)
    print(df.nlargest(20, "oos_calmar")[
        ["assets", "n_assets", "weights", "rebal_label", "experiment",
         "oos_return", "oos_sharpe", "oos_maxdd", "oos_calmar",
         "oos_trades", "vs_bh", "years", "trades_per_year"]
    ].to_string(index=False))
    print()

    # ── Top 20 Sharpe-to-MaxDD ──
    print("=" * 140)
    print("TOP 20 SHARPE-TO-MAXDD (OOS Sharpe / abs(MaxDD))")
    print("=" * 140)
    dv = df[df["oos_maxdd"] < 0].copy()
    if not dv.empty:
        dv["s2m"] = dv["oos_sharpe"] / dv["oos_maxdd"].abs()
        print(dv.nlargest(20, "s2m")[
            ["assets", "n_assets", "weights", "rebal_label", "experiment",
             "oos_return", "oos_sharpe", "oos_maxdd", "s2m",
             "oos_trades", "vs_bh", "years", "trades_per_year"]
        ].to_string(index=False))
    print()

    # ── Overall stats per experiment ──
    print("=" * 140)
    print("OVERALL STATISTICS BY EXPERIMENT")
    print("=" * 140)
    for exp_key in sorted(df["experiment"].unique()):
        sub = df[df["experiment"] == exp_key]
        if sub.empty:
            continue
        label = exp_labels.get(exp_key, exp_key)
        print(f"\n{label} ({len(sub):,} combos):")
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
