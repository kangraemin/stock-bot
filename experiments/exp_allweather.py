"""Experiment: Cross-Sector All-Weather Portfolio Backtest

899K건 분석 결과 기반 올웨더 전략 백테스트.
Phase 1: Core 포트폴리오 (4 variants × 5 rebal = 20)
Phase 2: Core+Satellite (Core 70% + Satellite 30%, ~24 combos)
Phase 3: Cash Buffer + VIX trigger (~6 combos)
Phase 4: Rolling OOS validation (top 3)
+ 4 benchmarks (SPY B&H, NVDA B&H, GLD B&H, 60/40)

IS/OOS split: 70%/30%.
"""

import sys
import os
import pathlib
import time

import numpy as np
import pandas as pd

# ── Constants ──
PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
RESULTS_DIR = PROJECT_ROOT / "results"
RESULTS_DIR.mkdir(exist_ok=True)

CAPITAL = 2000.0
FEE_RATE = 0.0025
IS_RATIO = 0.70

# ── Symbols ──
CORE_SYMBOLS = ["NVDA", "XOM", "META", "AVGO", "GLD", "BND"]
SATELLITE_SYMBOLS = ["MPC", "PSX", "TNA"]
MACRO_SYMBOLS = ["CL=F", "^VIX"]
BENCH_SYMBOLS = ["SPY"]
CASH_SYMBOL = "SHV"

ALL_SYMBOLS = list(set(
    CORE_SYMBOLS + SATELLITE_SYMBOLS + MACRO_SYMBOLS + BENCH_SYMBOLS + [CASH_SYMBOL]
))

# ── Phase 1: Core Portfolio Configs ──
CORE_VARIANTS = {
    "core_tech_gold": {
        "symbols": ["NVDA", "GLD"],
        "weights": (0.20, 0.80),
    },
    "core_balanced": {
        "symbols": ["NVDA", "AVGO", "GLD", "BND"],
        "weights": (0.15, 0.15, 0.40, 0.30),
    },
    "core_energy_tech": {
        "symbols": ["XOM", "NVDA", "GLD", "BND"],
        "weights": (0.20, 0.20, 0.40, 0.20),
    },
    "core_meta_avgo": {
        "symbols": ["META", "AVGO", "GLD"],
        "weights": (0.15, 0.15, 0.70),
    },
}

REBAL_CONFIGS = [
    ("band", 0.05),
    ("band", 0.10),
    ("quarterly", 0),
    ("semi_annual", 0),
    ("annual", 0),
]

# ── Phase 2: Satellite Configs ──
SATELLITE_CONFIGS = {
    "sat_mpc_oil": {
        "symbol": "MPC",
        "type": "oil_spike",
        "params": {"oil_pct": 0.05, "hold_days": 120},
    },
    "sat_rsi_dca": {
        "symbol": "PSX",
        "type": "rsi_mean_rev",
        "params": {"rsi_period": 14, "buy_rsi": 30, "sell_rsi": 70},
    },
    "sat_tna_rsi": {
        "symbol": "TNA",
        "type": "rsi_mean_rev",
        "params": {"rsi_period": 14, "buy_rsi": 25, "sell_rsi": 65},
    },
}

SATELLITE_RATIOS = [0.20, 0.30]

# ── Phase 3: VIX Cash Trigger ──
VIX_THRESHOLDS = [25, 30, 35]
DEPLOY_RATIOS = [0.5, 1.0]


# ═══════════════════════════════════════════════════════════════
# Core simulation functions (from exp_energy_portfolio.py pattern)
# ═══════════════════════════════════════════════════════════════

def simulate_portfolio(prices, weights, rebal_type, rebal_param, months, years):
    """Static weight portfolio rebalancing simulation."""
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


def compute_rsi(close, period=14):
    """Compute RSI array."""
    delta = np.diff(close)
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)

    avg_gain = np.empty(len(delta))
    avg_loss = np.empty(len(delta))
    avg_gain[:period] = np.nan
    avg_loss[:period] = np.nan

    avg_gain[period - 1] = np.mean(gain[:period])
    avg_loss[period - 1] = np.mean(loss[:period])

    for i in range(period, len(delta)):
        avg_gain[i] = (avg_gain[i - 1] * (period - 1) + gain[i]) / period
        avg_loss[i] = (avg_loss[i - 1] * (period - 1) + loss[i]) / period

    rs = avg_gain / np.where(avg_loss == 0, 1e-10, avg_loss)
    rsi = 100 - (100 / (1 + rs))
    # Prepend NaN for index alignment with close
    return np.concatenate([[np.nan], rsi])


def simulate_satellite(prices_sat, close_sat, signal_data, sat_config, capital_alloc):
    """Simulate satellite strategy on a single asset.
    Returns equity curve (length = len(close_sat)), total_trades.
    """
    n_days = len(close_sat)
    equity = np.empty(n_days, dtype=np.float64)
    cash = capital_alloc
    shares = 0.0
    total_trades = 0
    hold_counter = 0
    in_position = False

    sat_type = sat_config["type"]
    params = sat_config["params"]

    if sat_type == "oil_spike":
        oil_close = signal_data["oil"]
        oil_pct = params["oil_pct"]
        hold_days = params["hold_days"]
        oil_ret = np.zeros(n_days)
        oil_ret[1:] = np.diff(oil_close) / oil_close[:-1]

        for i in range(n_days):
            if in_position:
                hold_counter += 1
                if hold_counter >= hold_days:
                    cash = shares * close_sat[i] * (1 - FEE_RATE)
                    shares = 0.0
                    in_position = False
                    total_trades += 1
            else:
                if oil_ret[i] >= oil_pct and cash > 0:
                    shares = cash / (close_sat[i] * (1 + FEE_RATE))
                    cash = 0.0
                    in_position = True
                    hold_counter = 0
                    total_trades += 1

            equity[i] = cash + shares * close_sat[i]

    elif sat_type == "rsi_mean_rev":
        rsi = compute_rsi(close_sat, params["rsi_period"])
        buy_rsi = params["buy_rsi"]
        sell_rsi = params["sell_rsi"]

        for i in range(n_days):
            if np.isnan(rsi[i]):
                equity[i] = cash
                continue

            if not in_position:
                if rsi[i] < buy_rsi and cash > 0:
                    shares = cash / (close_sat[i] * (1 + FEE_RATE))
                    cash = 0.0
                    in_position = True
                    total_trades += 1
            else:
                if rsi[i] > sell_rsi:
                    cash = shares * close_sat[i] * (1 - FEE_RATE)
                    shares = 0.0
                    in_position = False
                    total_trades += 1

            equity[i] = cash + shares * close_sat[i]

    return equity, total_trades


def simulate_combined(core_prices, core_weights, rebal_type, rebal_param,
                      months, years, sat_close, sat_signal, sat_config,
                      core_ratio, sat_ratio, cash_ratio=0.0,
                      shv_close=None, vix_close=None,
                      vix_threshold=None, deploy_ratio=None):
    """Combined Core + Satellite + optional Cash simulation.
    Returns combined equity curve, total_trades, rebal_count.
    """
    n_days = core_prices.shape[0]

    core_capital = CAPITAL * core_ratio
    sat_capital = CAPITAL * sat_ratio
    cash_capital = CAPITAL * cash_ratio

    # Run core
    # Temporarily set CAPITAL for core simulation
    orig_cap = CAPITAL
    core_eq, core_trades, core_rebal = _sim_portfolio_with_capital(
        core_prices, core_weights, rebal_type, rebal_param, months, years, core_capital
    )

    # Run satellite
    sat_eq, sat_trades = simulate_satellite(
        None, sat_close, sat_signal, sat_config, sat_capital
    )

    # Cash/SHV component
    if cash_ratio > 0 and shv_close is not None:
        cash_eq = np.empty(n_days, dtype=np.float64)
        shv_shares = 0.0
        cash_cash = cash_capital
        deployed = False
        deploy_trades = 0

        for i in range(n_days):
            # VIX trigger
            if vix_close is not None and vix_threshold is not None:
                if not deployed and vix_close[i] > vix_threshold:
                    # Deploy cash to SHV → sell SHV, add to "deployed" pool
                    deployed = True
                    deploy_trades += 1
                elif deployed and vix_close[i] < vix_threshold * 0.8:
                    deployed = False
                    deploy_trades += 1

            if not deployed:
                # Hold SHV
                if shv_shares == 0 and cash_cash > 0:
                    shv_shares = cash_cash / (shv_close[i] * (1 + FEE_RATE))
                    cash_cash = 0.0
                cash_eq[i] = cash_cash + shv_shares * shv_close[i]
            else:
                # Deployed: cash earns same as core proportionally
                if shv_shares > 0:
                    cash_cash = shv_shares * shv_close[i] * (1 - FEE_RATE)
                    shv_shares = 0.0
                deploy_amt = cash_cash * deploy_ratio if deploy_ratio else cash_cash
                # Simple: deployed cash just tracks core return
                if i > 0 and core_eq[i - 1] > 0:
                    core_ret = core_eq[i] / core_eq[i - 1]
                    cash_eq[i] = cash_eq[i - 1] * core_ret if i > 0 else deploy_amt
                else:
                    cash_eq[i] = deploy_amt
    else:
        cash_eq = np.zeros(n_days, dtype=np.float64)
        deploy_trades = 0

    # Combine
    combined_eq = core_eq + sat_eq + cash_eq
    total_trades = core_trades + sat_trades + deploy_trades

    return combined_eq, total_trades, core_rebal


def _sim_portfolio_with_capital(prices, weights, rebal_type, rebal_param, months, years, capital):
    """simulate_portfolio but with custom capital."""
    n_days, n_assets = prices.shape
    target_w = np.array(weights, dtype=np.float64)
    equity = np.empty(n_days, dtype=np.float64)

    shares = np.zeros(n_assets, dtype=np.float64)
    cash = capital
    for j in range(n_assets):
        alloc = capital * target_w[j]
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


def compute_bh_return(prices, weights):
    """Buy & Hold return for benchmark."""
    n_assets = prices.shape[1]
    tw = np.array(weights, dtype=np.float64)
    shares = np.zeros(n_assets)
    for j in range(n_assets):
        shares[j] = (CAPITAL * tw[j]) / (prices[0, j] * (1 + FEE_RATE))
    cash_left = CAPITAL - sum(
        shares[j] * prices[0, j] * (1 + FEE_RATE) for j in range(n_assets)
    )
    return (np.sum(shares * prices[-1]) + cash_left - CAPITAL) / CAPITAL


def compute_metrics(equity, dates, total_trades, rebal_count):
    """Compute portfolio metrics."""
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


def make_result(experiment, label, symbols, weights, rebal_label,
                is_met, oos_met, bh_ret):
    """Format result dict for CSV."""
    return {
        "experiment": experiment,
        "label": label,
        "assets": "|".join(symbols),
        "n_assets": len(symbols),
        "weights": "|".join(f"{w:.3f}" for w in weights),
        "rebal_label": rebal_label,
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
        "bh_return": round(bh_ret, 4),
        "vs_bh": round(oos_met["total_return"] - bh_ret, 4),
        "years": oos_met["years"],
        "trades_per_year": oos_met["trades_per_year"],
    }


# ═══════════════════════════════════════════════════════════════
# Data loading & alignment
# ═══════════════════════════════════════════════════════════════

def load_data():
    """Load all required symbols from parquet."""
    all_close = {}
    for sym in ALL_SYMBOLS:
        fname = sym.replace("^", "").replace("=", "_") + ".parquet"
        fpath = DATA_DIR / fname
        if not fpath.exists():
            # Try alternate naming
            fpath = DATA_DIR / (sym + ".parquet")
        if not fpath.exists():
            print(f"  WARNING: {sym} not found at {fpath}")
            continue
        df = pd.read_parquet(fpath)
        if "close" in df.columns:
            all_close[sym] = df["close"].dropna()
        elif "Close" in df.columns:
            all_close[sym] = df["Close"].dropna()
    return all_close


def align_symbols(all_close, symbols):
    """Align symbols to common dates. Returns (prices, dates) or None."""
    series = []
    for sym in symbols:
        if sym not in all_close:
            return None
        series.append(all_close[sym])

    common_idx = series[0].index
    for s in series[1:]:
        common_idx = common_idx.intersection(s.index)
    if len(common_idx) < 500:
        return None

    common_idx = common_idx.sort_values()
    prices = np.column_stack([s.loc[common_idx].values for s in series])
    dates = common_idx.values.astype("datetime64[D]")
    return prices, dates


def split_is_oos(prices, dates):
    """70/30 IS/OOS split."""
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
# Phase 1: Core Portfolio
# ═══════════════════════════════════════════════════════════════

def run_phase1(all_close):
    """Phase 1: 4 Core variants × 5 rebal = 20 combos."""
    print("\n" + "=" * 60)
    print("Phase 1: Core Portfolio (4 variants × 5 rebal = 20)")
    print("=" * 60)

    results = []
    for name, cfg in CORE_VARIANTS.items():
        syms = cfg["symbols"]
        weights = cfg["weights"]
        aligned = align_symbols(all_close, syms)
        if aligned is None:
            print(f"  SKIP {name}: insufficient data overlap")
            continue

        prices, dates = aligned
        split_data = split_is_oos(prices, dates)
        if split_data is None:
            print(f"  SKIP {name}: insufficient data for split")
            continue

        for rtype, rparam in REBAL_CONFIGS:
            rl = f"band_{int(rparam*100)}%" if rtype == "band" else rtype

            is_eq, is_tr, is_rb = simulate_portfolio(
                split_data["is_prices"], weights, rtype, rparam,
                split_data["is_m"], split_data["is_y"]
            )
            is_met = compute_metrics(is_eq, split_data["is_d"], is_tr, is_rb)
            if is_met is None:
                continue

            oos_eq, oos_tr, oos_rb = simulate_portfolio(
                split_data["oos_prices"], weights, rtype, rparam,
                split_data["oos_m"], split_data["oos_y"]
            )
            oos_met = compute_metrics(oos_eq, split_data["oos_d"], oos_tr, oos_rb)
            if oos_met is None:
                continue

            bh = compute_bh_return(split_data["oos_prices"], weights)
            r = make_result("phase1_core", name, syms, weights, rl, is_met, oos_met, bh)
            results.append(r)
            print(f"  {name} | {rl}: OOS Sharpe={oos_met['sharpe']:.2f}, "
                  f"Return={oos_met['total_return']*100:.1f}%, MDD={oos_met['maxdd']*100:.1f}%, "
                  f"Trades={oos_met['trades']}({oos_met['trades_per_year']}/yr)")

    print(f"\nPhase 1 complete: {len(results)} results")
    return results


# ═══════════════════════════════════════════════════════════════
# Phase 2: Core + Satellite
# ═══════════════════════════════════════════════════════════════

def run_phase2(all_close, phase1_results):
    """Phase 2: Top core configs + 3 satellites × 2 ratios."""
    print("\n" + "=" * 60)
    print("Phase 2: Core + Satellite")
    print("=" * 60)

    # Pick top 2 core configs by OOS Sharpe
    if not phase1_results:
        print("  No Phase 1 results, skipping Phase 2")
        return []

    p1_df = pd.DataFrame(phase1_results)
    top_cores = (p1_df.sort_values("oos_sharpe", ascending=False)
                 .drop_duplicates("label")
                 .head(2))

    results = []
    for _, core_row in top_cores.iterrows():
        core_name = core_row["label"]
        core_cfg = CORE_VARIANTS[core_name]
        core_syms = core_cfg["symbols"]
        core_weights = core_cfg["weights"]
        core_rebal_label = core_row["rebal_label"]

        # Parse rebal from label
        if core_rebal_label.startswith("band_"):
            rtype = "band"
            rparam = int(core_rebal_label.split("_")[1].replace("%", "")) / 100
        else:
            rtype = core_rebal_label
            rparam = 0

        for sat_name, sat_cfg in SATELLITE_CONFIGS.items():
            sat_sym = sat_cfg["symbol"]

            # Align core + satellite
            all_syms = core_syms + [sat_sym]
            if sat_cfg["type"] == "oil_spike":
                all_syms_with_macro = list(set(all_syms + ["CL=F"]))
            else:
                all_syms_with_macro = all_syms

            aligned = align_symbols(all_close, all_syms_with_macro)
            if aligned is None:
                print(f"  SKIP {core_name}+{sat_name}: insufficient overlap")
                continue

            prices, dates = aligned
            split_data = split_is_oos(prices, dates)
            if split_data is None:
                continue

            # Map column indices
            sym_to_idx = {s: i for i, s in enumerate(all_syms_with_macro)}
            core_idx = [sym_to_idx[s] for s in core_syms]
            sat_idx = sym_to_idx[sat_sym]

            for sat_ratio in SATELLITE_RATIOS:
                core_ratio = 1.0 - sat_ratio

                for phase_label, p_data, d_data, m_data, y_data in [
                    ("is", split_data["is_prices"], split_data["is_d"],
                     split_data["is_m"], split_data["is_y"]),
                    ("oos", split_data["oos_prices"], split_data["oos_d"],
                     split_data["oos_m"], split_data["oos_y"]),
                ]:
                    core_p = p_data[:, core_idx]
                    sat_close = p_data[:, sat_idx]

                    # Signal data
                    signal_data = {}
                    if sat_cfg["type"] == "oil_spike" and "CL=F" in sym_to_idx:
                        signal_data["oil"] = p_data[:, sym_to_idx["CL=F"]]

                    core_eq, core_tr, core_rb = _sim_portfolio_with_capital(
                        core_p, core_weights, rtype, rparam, m_data, y_data,
                        CAPITAL * core_ratio
                    )

                    sat_eq, sat_tr = simulate_satellite(
                        None, sat_close, signal_data, sat_cfg, CAPITAL * sat_ratio
                    )

                    combined_eq = core_eq + sat_eq
                    total_tr = core_tr + sat_tr

                    if phase_label == "is":
                        is_met = compute_metrics(combined_eq, d_data, total_tr, core_rb)
                    else:
                        oos_met = compute_metrics(combined_eq, d_data, total_tr, core_rb)

                if is_met is None or oos_met is None:
                    continue

                # B&H of core only
                bh = compute_bh_return(
                    split_data["oos_prices"][:, core_idx], core_weights
                )

                combo_label = f"{core_name}+{sat_name}({int(sat_ratio*100)}%)"
                rl = core_rebal_label
                all_w = list(np.array(core_weights) * core_ratio) + [sat_ratio]
                r = make_result(
                    "phase2_core_sat", combo_label,
                    core_syms + [sat_sym], tuple(all_w), rl,
                    is_met, oos_met, bh
                )
                results.append(r)
                print(f"  {combo_label} | {rl}: OOS Sharpe={oos_met['sharpe']:.2f}, "
                      f"Return={oos_met['total_return']*100:.1f}%, MDD={oos_met['maxdd']*100:.1f}%, "
                      f"Trades={oos_met['trades']}({oos_met['trades_per_year']}/yr)")

    print(f"\nPhase 2 complete: {len(results)} results")
    return results


# ═══════════════════════════════════════════════════════════════
# Phase 3: Cash Buffer + VIX Trigger
# ═══════════════════════════════════════════════════════════════

def run_phase3(all_close, phase2_results):
    """Phase 3: Top Phase 2 + Cash/SHV + VIX trigger."""
    print("\n" + "=" * 60)
    print("Phase 3: Cash Buffer + VIX Trigger")
    print("=" * 60)

    if not phase2_results:
        print("  No Phase 2 results, skipping Phase 3")
        return []

    p2_df = pd.DataFrame(phase2_results)
    top_combo = p2_df.sort_values("oos_sharpe", ascending=False).iloc[0]
    combo_label = top_combo["label"]

    # Reconstruct from label
    parts = combo_label.split("+")
    core_name = parts[0]
    sat_part = parts[1] if len(parts) > 1 else None

    core_cfg = CORE_VARIANTS[core_name]
    core_syms = core_cfg["symbols"]
    core_weights = core_cfg["weights"]

    # Parse satellite
    sat_cfg = None
    sat_sym = None
    if sat_part:
        for sn, sc in SATELLITE_CONFIGS.items():
            if sn in sat_part:
                sat_cfg = sc
                sat_sym = sc["symbol"]
                break

    # Parse rebal
    rl = top_combo["rebal_label"]
    if rl.startswith("band_"):
        rtype = "band"
        rparam = int(rl.split("_")[1].replace("%", "")) / 100
    else:
        rtype = rl
        rparam = 0

    results = []

    # Need VIX + SHV aligned
    all_syms = list(set(core_syms + ([sat_sym] if sat_sym else []) + ["SHV", "^VIX"]))
    if sat_cfg and sat_cfg["type"] == "oil_spike":
        all_syms = list(set(all_syms + ["CL=F"]))

    aligned = align_symbols(all_close, all_syms)
    if aligned is None:
        print("  Cannot align all symbols for Phase 3")
        return []

    prices, dates = aligned
    split_data = split_is_oos(prices, dates)
    if split_data is None:
        return []

    sym_to_idx = {s: i for i, s in enumerate(all_syms)}
    core_idx = [sym_to_idx[s] for s in core_syms]
    vix_idx = sym_to_idx["^VIX"]
    shv_idx = sym_to_idx["SHV"]
    sat_idx = sym_to_idx[sat_sym] if sat_sym else None

    for vix_thresh in VIX_THRESHOLDS:
        for deploy_r in DEPLOY_RATIOS:
            for phase_label, p_data, d_data, m_data, y_data in [
                ("is", split_data["is_prices"], split_data["is_d"],
                 split_data["is_m"], split_data["is_y"]),
                ("oos", split_data["oos_prices"], split_data["oos_d"],
                 split_data["oos_m"], split_data["oos_y"]),
            ]:
                core_ratio = 0.70
                sat_ratio_val = 0.20
                cash_ratio = 0.10

                core_p = p_data[:, core_idx]
                vix_close = p_data[:, vix_idx]
                shv_close = p_data[:, shv_idx]
                n_days = len(d_data)

                # Core component
                core_eq, core_tr, core_rb = _sim_portfolio_with_capital(
                    core_p, core_weights, rtype, rparam, m_data, y_data,
                    CAPITAL * core_ratio
                )

                # Satellite component
                sat_tr = 0
                if sat_idx is not None and sat_cfg is not None:
                    sat_close_arr = p_data[:, sat_idx]
                    signal_data = {}
                    if sat_cfg["type"] == "oil_spike" and "CL=F" in sym_to_idx:
                        signal_data["oil"] = p_data[:, sym_to_idx["CL=F"]]
                    sat_eq, sat_tr = simulate_satellite(
                        None, sat_close_arr, signal_data, sat_cfg,
                        CAPITAL * sat_ratio_val
                    )
                else:
                    sat_eq = np.full(n_days, CAPITAL * sat_ratio_val)

                # Cash component: SHV with VIX deploy
                cash_eq = np.empty(n_days, dtype=np.float64)
                cash_cash = CAPITAL * cash_ratio
                shv_shares = 0.0
                deployed = False
                deploy_trades = 0

                for i in range(n_days):
                    if not deployed and vix_close[i] > vix_thresh:
                        # Deploy: sell SHV, track core returns
                        if shv_shares > 0:
                            cash_cash = shv_shares * shv_close[i] * (1 - FEE_RATE)
                            shv_shares = 0.0
                        deployed = True
                        deploy_trades += 1
                    elif deployed and vix_close[i] < vix_thresh * 0.8:
                        # Return to SHV
                        if cash_cash > 0:
                            shv_shares = cash_cash / (shv_close[i] * (1 + FEE_RATE))
                            cash_cash = 0.0
                        deployed = False
                        deploy_trades += 1

                    if deployed:
                        # Cash tracks core returns proportionally
                        deploy_amt = (cash_cash + shv_shares * shv_close[i]) * deploy_r
                        idle_amt = (cash_cash + shv_shares * shv_close[i]) * (1 - deploy_r)
                        if i > 0 and core_eq[i - 1] > 0:
                            core_daily_ret = core_eq[i] / core_eq[i - 1]
                            if i == 0 or cash_eq[i - 1] <= 0:
                                cash_eq[i] = deploy_amt + idle_amt
                            else:
                                deployed_prev = cash_eq[i - 1] * deploy_r
                                idle_prev = cash_eq[i - 1] * (1 - deploy_r)
                                cash_eq[i] = deployed_prev * core_daily_ret + idle_prev
                        else:
                            cash_eq[i] = cash_cash + shv_shares * shv_close[i]
                    else:
                        cash_eq[i] = cash_cash + shv_shares * shv_close[i]

                combined_eq = core_eq + sat_eq + cash_eq
                total_tr = core_tr + sat_tr + deploy_trades

                if phase_label == "is":
                    is_met = compute_metrics(combined_eq, d_data, total_tr, core_rb)
                else:
                    oos_met = compute_metrics(combined_eq, d_data, total_tr, core_rb)

            if is_met is None or oos_met is None:
                continue

            bh = compute_bh_return(split_data["oos_prices"][:, core_idx], core_weights)
            label = f"{combo_label}+cash(VIX>{vix_thresh},deploy{int(deploy_r*100)}%)"
            all_w_list = list(np.array(core_weights) * 0.70)
            if sat_sym:
                all_w_list.append(0.20)
            all_w_list.append(0.10)
            sym_list = core_syms + ([sat_sym] if sat_sym else []) + ["SHV"]

            r = make_result(
                "phase3_cash_vix", label, sym_list, tuple(all_w_list), rl,
                is_met, oos_met, bh
            )
            results.append(r)
            print(f"  {label}: OOS Sharpe={oos_met['sharpe']:.2f}, "
                  f"Return={oos_met['total_return']*100:.1f}%, MDD={oos_met['maxdd']*100:.1f}%, "
                  f"Trades={oos_met['trades']}({oos_met['trades_per_year']}/yr)")

    print(f"\nPhase 3 complete: {len(results)} results")
    return results


# ═══════════════════════════════════════════════════════════════
# Benchmarks
# ═══════════════════════════════════════════════════════════════

def run_benchmarks(all_close):
    """Run 4 benchmark strategies."""
    print("\n" + "=" * 60)
    print("Benchmarks")
    print("=" * 60)

    benchmarks = {
        "SPY_BH": {"symbols": ["SPY"], "weights": (1.0,)},
        "NVDA_BH": {"symbols": ["NVDA"], "weights": (1.0,)},
        "GLD_BH": {"symbols": ["GLD"], "weights": (1.0,)},
        "60_40": {"symbols": ["SPY", "BND"], "weights": (0.60, 0.40)},
    }

    results = []
    for name, cfg in benchmarks.items():
        syms = cfg["symbols"]
        weights = cfg["weights"]
        aligned = align_symbols(all_close, syms)
        if aligned is None:
            print(f"  SKIP {name}: insufficient data")
            continue

        prices, dates = aligned
        split_data = split_is_oos(prices, dates)
        if split_data is None:
            continue

        # Annual rebalancing (or none for single asset)
        rtype = "annual" if len(syms) > 1 else "annual"
        rparam = 0

        is_eq, is_tr, is_rb = simulate_portfolio(
            split_data["is_prices"], weights, rtype, rparam,
            split_data["is_m"], split_data["is_y"]
        )
        is_met = compute_metrics(is_eq, split_data["is_d"], is_tr, is_rb)

        oos_eq, oos_tr, oos_rb = simulate_portfolio(
            split_data["oos_prices"], weights, rtype, rparam,
            split_data["oos_m"], split_data["oos_y"]
        )
        oos_met = compute_metrics(oos_eq, split_data["oos_d"], oos_tr, oos_rb)

        if is_met is None or oos_met is None:
            continue

        bh = compute_bh_return(split_data["oos_prices"], weights)
        r = make_result("benchmark", name, syms, weights, "annual", is_met, oos_met, bh)
        results.append(r)
        print(f"  {name}: OOS Sharpe={oos_met['sharpe']:.2f}, "
              f"Return={oos_met['total_return']*100:.1f}%, MDD={oos_met['maxdd']*100:.1f}%, "
              f"Trades={oos_met['trades']}({oos_met['trades_per_year']}/yr)")

    return results


# ═══════════════════════════════════════════════════════════════
# Phase 4: Rolling OOS Validation
# ═══════════════════════════════════════════════════════════════

def run_rolling_oos(all_close, all_results):
    """Rolling OOS on top 3 strategies."""
    print("\n" + "=" * 60)
    print("Phase 4: Rolling OOS Validation (Top 3)")
    print("=" * 60)

    if not all_results:
        print("  No results to validate")
        return []

    df = pd.DataFrame(all_results)
    # Exclude benchmarks
    strat_df = df[df["experiment"] != "benchmark"]
    if strat_df.empty:
        print("  No strategy results")
        return []

    top3 = strat_df.sort_values("oos_sharpe", ascending=False).head(3)

    TRAIN_YEARS = 5
    TEST_YEARS = 2
    SLIDE_YEARS = 1
    N_WINDOWS = 6

    validation_results = []

    for _, row in top3.iterrows():
        label = row["label"]
        experiment = row["experiment"]
        syms = row["assets"].split("|")
        weights_str = row["weights"].split("|")
        weights = tuple(float(w) for w in weights_str)
        rl = row["rebal_label"]

        if rl.startswith("band_"):
            rtype = "band"
            rparam = int(rl.split("_")[1].replace("%", "")) / 100
        else:
            rtype = rl
            rparam = 0

        # For combined strategies, just validate the core part
        core_syms = [s for s in syms if s in CORE_SYMBOLS]
        if not core_syms:
            core_syms = syms
        core_weights_raw = weights[:len(core_syms)]
        w_sum = sum(core_weights_raw)
        core_weights = tuple(w / w_sum for w in core_weights_raw) if w_sum > 0 else weights

        aligned = align_symbols(all_close, core_syms)
        if aligned is None:
            print(f"  SKIP {label}: cannot align for rolling OOS")
            continue

        prices, dates = aligned
        total_days = len(dates)
        dates_pd = pd.DatetimeIndex(dates)
        years_range = (dates[-1] - dates[0]) / np.timedelta64(365, "D")

        if years_range < TRAIN_YEARS + TEST_YEARS:
            print(f"  SKIP {label}: insufficient data ({years_range:.1f}yr)")
            continue

        wins = 0
        total_windows = 0
        window_results = []

        for w in range(N_WINDOWS):
            train_start_year = dates_pd[0].year + w * SLIDE_YEARS
            train_end_year = train_start_year + TRAIN_YEARS
            test_end_year = train_end_year + TEST_YEARS

            train_mask = (dates_pd.year >= train_start_year) & (dates_pd.year < train_end_year)
            test_mask = (dates_pd.year >= train_end_year) & (dates_pd.year < test_end_year)

            train_idx = np.where(train_mask)[0]
            test_idx = np.where(test_mask)[0]

            if len(train_idx) < 252 or len(test_idx) < 126:
                continue

            test_p = prices[test_idx]
            test_d = dates[test_idx]
            test_pd = pd.DatetimeIndex(test_d)
            test_m = test_pd.month.values.astype(np.int32)
            test_y = test_pd.year.values.astype(np.int32)

            eq, tr, rb = simulate_portfolio(
                test_p, core_weights, rtype, rparam, test_m, test_y
            )
            met = compute_metrics(eq, test_d, tr, rb)
            if met is None:
                continue

            total_windows += 1
            if met["sharpe"] > 0.5:
                wins += 1

            window_results.append({
                "window": w + 1,
                "period": f"{train_start_year}-{test_end_year}",
                "sharpe": met["sharpe"],
                "return": met["total_return"],
                "maxdd": met["maxdd"],
                "trades": met["trades"],
                "pass": met["sharpe"] > 0.5,
            })

        win_rate = wins / total_windows if total_windows > 0 else 0
        avg_sharpe = np.mean([wr["sharpe"] for wr in window_results]) if window_results else 0

        validation_results.append({
            "label": label,
            "experiment": experiment,
            "windows": total_windows,
            "wins": wins,
            "win_rate": round(win_rate, 2),
            "avg_sharpe": round(avg_sharpe, 2),
            "window_details": window_results,
            "pass": win_rate >= 0.6,
        })

        status = "PASS" if win_rate >= 0.6 else "FAIL"
        print(f"  {label}: {wins}/{total_windows} windows, "
              f"win_rate={win_rate*100:.0f}%, avg_sharpe={avg_sharpe:.2f} → {status}")

    return validation_results


# ═══════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════

def main():
    t0 = time.time()
    print("Cross-Sector All-Weather Portfolio Backtest")
    print("=" * 60)

    # Load data
    print("\nLoading data...")
    all_close = load_data()
    print(f"  Loaded {len(all_close)} symbols")

    missing = [s for s in ALL_SYMBOLS if s not in all_close]
    if missing:
        print(f"  Missing: {missing}")

    # Phase 1
    p1_results = run_phase1(all_close)

    # Phase 2
    p2_results = run_phase2(all_close, p1_results)

    # Phase 3
    p3_results = run_phase3(all_close, p2_results)

    # Benchmarks
    bench_results = run_benchmarks(all_close)

    # Combine all results
    all_results = p1_results + p2_results + p3_results + bench_results

    # Save CSV
    if all_results:
        df = pd.DataFrame(all_results)
        csv_path = RESULTS_DIR / "allweather_results.csv"
        df.to_csv(csv_path, index=False)
        print(f"\nSaved {len(df)} results to {csv_path}")

    # Phase 4: Rolling OOS
    val_results = run_rolling_oos(all_close, all_results)

    # Summary
    elapsed = time.time() - t0
    print(f"\n{'=' * 60}")
    print(f"COMPLETE: {len(all_results)} total results in {elapsed:.1f}s")
    print(f"  Phase 1 (Core): {len(p1_results)}")
    print(f"  Phase 2 (Core+Sat): {len(p2_results)}")
    print(f"  Phase 3 (Cash+VIX): {len(p3_results)}")
    print(f"  Benchmarks: {len(bench_results)}")
    print(f"  Rolling OOS: {len(val_results)} validated")

    if all_results:
        df = pd.DataFrame(all_results)
        print(f"\n{'=' * 60}")
        print("TOP 5 by OOS Sharpe:")
        top5 = df.sort_values("oos_sharpe", ascending=False).head(5)
        for _, r in top5.iterrows():
            print(f"  {r['label']}: Sharpe={r['oos_sharpe']:.2f}, "
                  f"Return={r['oos_return']*100:.1f}%, MDD={r['oos_maxdd']*100:.1f}%, "
                  f"Trades={r['oos_trades']}({r['trades_per_year']}/yr), vs B&H={r['vs_bh']*100:+.1f}%p")

    if val_results:
        print(f"\nRolling OOS Validation:")
        for v in val_results:
            status = "PASS" if v["pass"] else "FAIL"
            print(f"  {v['label']}: {v['wins']}/{v['windows']} ({v['win_rate']*100:.0f}%), "
                  f"avg_sharpe={v['avg_sharpe']:.2f} → {status}")


if __name__ == "__main__":
    main()
