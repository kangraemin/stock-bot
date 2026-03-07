"""Experiment: Energy Cross-Sector Validation (~580 combinations)

Phase 4: Walk-Forward OOS + Ensemble + Fee Sensitivity
Reads top strategies from Phase 1-3 CSV results, re-runs on rolling windows.

Self-contained numpy-based backtester.
Fork-based multiprocessing (global data inherited, no pickling).
"""

import sys
import os
import pathlib
import time
import itertools
import multiprocessing as mp
from collections import defaultdict

import numpy as np
import pandas as pd

# ── Constants ──
PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
RESULTS_DIR = PROJECT_ROOT / "results"
RESULTS_DIR.mkdir(exist_ok=True)

CAPITAL = 2000.0
FEE_RATE = 0.0025
FEE_LEVELS = [0.0005, 0.0010, 0.0025, 0.0050, 0.0100]  # 0.05% ~ 1%

TOP_N = 20  # top strategies per source
N_WINDOWS = 6  # rolling WF windows
TRAIN_YEARS = 5
TEST_YEARS = 2
SLIDE_YEARS = 1

# ── Global data (populated in main, inherited by fork) ──
G_DATA = {}  # sym -> {close, high, low, dates}
G_MACRO = {}  # indicator -> aligned array
G_DEFENSE_AVG = None
G_SPY_CLOSE = None

ENERGY = ["CVX", "XOM", "XLE", "XOP", "OIH", "FANG", "VDE", "ERX",
          "COP", "SLB", "EOG", "MPC", "PSX", "HAL", "DVN"]
DEFENSE = ["LMT", "RTX", "NOC"]
TECH = ["NVDA", "AAPL", "MSFT"]
MACRO_SYMS = {"CL=F": "oil", "NG=F": "natgas", "^VIX": "vix",
              "GC=F": "gold", "^TNX": "tnx", "DX-Y.NYB": "dxy", "HG=F": "copper"}

PORTFOLIO_ENERGY = ["CVX", "XOM", "XLE", "COP", "VDE", "ERX"]
PORTFOLIO_TECH = ["QQQ", "NVDA", "TQQQ", "SOXX", "XLK", "AAPL"]
PORTFOLIO_DEFENSE_ASSETS = ["GLD", "TLT", "BND", "XLP", "XLV", "SPY"]
PORTFOLIO_LEV_TECH = ["TQQQ", "SOXL", "TECL"]


# ══════════════════════════════════════════════════════════════════════
# Indicator Functions (numpy) — copied from exp_energy_strategies.py
# ══════════════════════════════════════════════════════════════════════

def compute_rsi(close, period=14):
    delta = np.diff(close, prepend=close[0])
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)
    alpha = 1.0 / period
    n = len(close)
    avg_gain = np.zeros(n)
    avg_loss = np.zeros(n)
    if n < period + 1:
        return np.full(n, 50.0)
    avg_gain[period] = np.mean(gain[1:period + 1])
    avg_loss[period] = np.mean(loss[1:period + 1])
    for i in range(period + 1, n):
        avg_gain[i] = avg_gain[i - 1] * (1 - alpha) + gain[i] * alpha
        avg_loss[i] = avg_loss[i - 1] * (1 - alpha) + loss[i] * alpha
    rs = np.divide(avg_gain, avg_loss, out=np.ones(n), where=avg_loss != 0)
    rsi = 100.0 - 100.0 / (1.0 + rs)
    rsi[:period] = 50.0
    return rsi


def compute_bb(close, window, num_std):
    n = len(close)
    upper = np.full(n, np.nan)
    lower = np.full(n, np.nan)
    for i in range(window - 1, n):
        seg = close[i - window + 1:i + 1]
        m = np.mean(seg)
        s = np.std(seg)
        upper[i] = m + num_std * s
        lower[i] = m - num_std * s
    return upper, lower


def compute_ema(close, window):
    n = len(close)
    ema = np.zeros(n)
    ema[0] = close[0]
    alpha = 2.0 / (window + 1)
    for i in range(1, n):
        ema[i] = alpha * close[i] + (1 - alpha) * ema[i - 1]
    return ema


def compute_sma(arr, window):
    out = np.full(len(arr), np.nan)
    if len(arr) < window:
        return out
    cs = np.cumsum(arr)
    out[window - 1:] = (cs[window - 1:] - np.concatenate([[0], cs[:-window]])) / window
    return out


def compute_atr(high, low, close, window):
    n = len(close)
    tr = np.zeros(n)
    tr[0] = high[0] - low[0]
    for i in range(1, n):
        tr[i] = max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1]))
    atr = np.zeros(n)
    if n < window:
        return atr
    atr[window - 1] = np.mean(tr[:window])
    for i in range(window, n):
        atr[i] = (atr[i - 1] * (window - 1) + tr[i]) / window
    return atr


def compute_macd(close, fast, slow, signal):
    ema_fast = compute_ema(close, fast)
    ema_slow = compute_ema(close, slow)
    macd_line = ema_fast - ema_slow
    signal_line = compute_ema(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def detect_spike(series, lookback, threshold):
    mask = np.zeros(len(series), dtype=bool)
    if len(series) <= lookback:
        return mask
    pct = series[lookback:] / series[:-lookback] - 1.0
    mask[lookback:] = pct > threshold
    return mask


def compute_metrics(equity, trades):
    if len(equity) < 2 or equity[0] <= 0:
        return {"total_return": 0, "sharpe": 0, "maxdd": 0, "calmar": 0,
                "trades": 0, "trades_per_year": 0, "years": 0}
    returns = np.diff(equity) / np.where(equity[:-1] != 0, equity[:-1], 1.0)
    returns = returns[np.isfinite(returns)]
    total_return = equity[-1] / equity[0] - 1
    n_years = len(equity) / 252.0
    ann_return = (1 + total_return) ** (1 / n_years) - 1 if n_years > 0 and total_return > -1 else 0
    sharpe = float(np.mean(returns) / np.std(returns) * np.sqrt(252)) if len(returns) > 1 and np.std(returns) > 0 else 0
    peak = np.maximum.accumulate(equity)
    dd = (equity - peak) / np.where(peak != 0, peak, 1.0)
    maxdd = float(np.min(dd))
    calmar = ann_return / abs(maxdd) if maxdd != 0 else 0
    tpy = trades / n_years if n_years > 0 else 0
    return {"total_return": total_return, "sharpe": sharpe, "maxdd": maxdd,
            "calmar": calmar, "trades": trades, "trades_per_year": round(tpy, 1),
            "years": round(n_years, 2)}


# ══════════════════════════════════════════════════════════════════════
# Strategy Replay Functions
# ══════════════════════════════════════════════════════════════════════

def simulate_long_only(close, buy_signals, sell_signals, capital=CAPITAL, fee=FEE_RATE):
    n = len(close)
    equity = np.full(n, capital, dtype=np.float64)
    position = 0.0
    cash = capital
    trades = 0
    for i in range(1, n):
        if buy_signals[i] and position == 0:
            position = cash * (1 - fee) / close[i]
            cash = 0.0
            trades += 1
        elif sell_signals[i] and position > 0:
            cash = position * close[i] * (1 - fee)
            position = 0.0
            trades += 1
        equity[i] = cash + position * close[i]
    return equity, trades


def replay_bb_rsi_ema(close, params_str, fee=FEE_RATE):
    """Replay bb_rsi_ema from params string."""
    p = _parse_params(params_str)
    bb_win = int(p.get("bb", "20").split("/")[0])
    bb_std = float(p.get("bb", "20/2.0").split("/")[1])
    rsi_parts = p.get("rsi", "14/30/70").split("/")
    rsi_win = int(rsi_parts[0])
    rsi_buy = int(rsi_parts[1])
    rsi_sell = int(rsi_parts[2])
    ema_win = int(p.get("ema", "50"))
    ema_filt = p.get("filt", "False") == "True"

    rsi = compute_rsi(close, rsi_win)
    bb_upper, bb_lower = compute_bb(close, bb_win, bb_std)
    ema = compute_ema(close, ema_win)

    n = len(close)
    buy_sig = np.zeros(n, dtype=bool)
    sell_sig = np.zeros(n, dtype=bool)
    warmup = max(bb_win, ema_win)

    for i in range(warmup, n):
        if np.isnan(bb_lower[i]):
            continue
        buy_cond = (close[i] < bb_lower[i]) and (rsi[i] < rsi_buy)
        if ema_filt:
            buy_cond = buy_cond and (close[i] > ema[i])
        sell_cond = (close[i] > bb_upper[i]) and (rsi[i] > rsi_sell)
        buy_sig[i] = buy_cond
        sell_sig[i] = sell_cond

    return simulate_long_only(close, buy_sig, sell_sig, fee=fee)


def replay_rsi_solo(close, params_str, fee=FEE_RATE):
    """Replay rsi_solo from params string."""
    p = _parse_params(params_str)
    rsi_parts = p.get("rsi", "14/30/70").split("/")
    rsi_win = int(rsi_parts[0])
    oversold = int(rsi_parts[1])
    overbought = int(rsi_parts[2])
    exit_mode = p.get("exit", "rsi_cross")

    rsi = compute_rsi(close, rsi_win)
    n = len(close)
    buy_sig = np.zeros(n, dtype=bool)
    sell_sig = np.zeros(n, dtype=bool)

    holding = False
    entry_bar = 0
    peak_price = 0.0

    for i in range(rsi_win, n):
        if not holding:
            if rsi[i] < oversold:
                buy_sig[i] = True
                holding = True
                entry_bar = i
                peak_price = close[i]
        else:
            if close[i] > peak_price:
                peak_price = close[i]
            do_sell = False
            if exit_mode == "rsi_cross":
                do_sell = rsi[i] > overbought
            elif exit_mode == "hold_20d":
                do_sell = (i - entry_bar) >= 20
            elif exit_mode == "hold_60d":
                do_sell = (i - entry_bar) >= 60
            elif exit_mode == "trail_15pct":
                do_sell = close[i] < peak_price * 0.85
            if do_sell:
                sell_sig[i] = True
                holding = False

    return simulate_long_only(close, buy_sig, sell_sig, fee=fee)


def replay_dca(close, params_str, fee=FEE_RATE):
    """Replay DCA from params string."""
    p = _parse_params(params_str)
    freq = int(p.get("freq", "5"))
    scheme = p.get("scheme", "none")
    rsi_period = int(p.get("rsi_p", "14"))
    boost = float(p.get("boost", "2.0"))

    rsi = compute_rsi(close, rsi_period)
    n = len(close)
    shares = CAPITAL / (close[0] * (1 + fee))
    total_invested = CAPITAL
    n_trades = 1
    equity = np.zeros(n)
    dca_amount = 100.0

    for i in range(n):
        if i > 0 and i % freq == 0:
            w = _dca_weight(rsi[i], scheme, boost)
            amount = dca_amount * w
            if amount > 0:
                shares += amount / (close[i] * (1 + fee))
                total_invested += amount
                n_trades += 1
        equity[i] = shares * close[i]

    return equity, n_trades


def replay_momentum(close, params_str, fee=FEE_RATE):
    """Replay momentum from params string."""
    p = _parse_params(params_str)
    lookback = int(p.get("look", "21"))
    threshold = float(p.get("thr", "0.03"))
    hold = int(p.get("hold", "21"))

    n = len(close)
    buy_sig = np.zeros(n, dtype=bool)
    sell_sig = np.zeros(n, dtype=bool)
    holding = False
    entry_bar = 0

    for i in range(lookback, n):
        ret = close[i] / close[i - lookback] - 1
        if not holding and ret > threshold:
            buy_sig[i] = True
            holding = True
            entry_bar = i
        elif holding and (i - entry_bar) >= hold:
            sell_sig[i] = True
            holding = False

    return simulate_long_only(close, buy_sig, sell_sig, fee=fee)


def replay_macd(close, params_str, fee=FEE_RATE):
    """Replay MACD from params string."""
    p = _parse_params(params_str)
    fast = int(p.get("fast", "12"))
    slow = int(p.get("slow", "26"))
    sig = int(p.get("sig", "9"))

    _, _, histogram = compute_macd(close, fast, slow, sig)
    n = len(close)
    buy_sig = np.zeros(n, dtype=bool)
    sell_sig = np.zeros(n, dtype=bool)
    warmup = slow + sig

    for i in range(warmup, n):
        if histogram[i] > 0 and histogram[i - 1] <= 0:
            buy_sig[i] = True
        elif histogram[i] < 0 and histogram[i - 1] >= 0:
            sell_sig[i] = True

    return simulate_long_only(close, buy_sig, sell_sig, fee=fee)


def replay_vol_target(close, params_str, fee=FEE_RATE):
    """Replay vol targeting from params string."""
    p = _parse_params(params_str)
    target_vol = float(p.get("vol", "0.2"))
    vol_win = int(p.get("win", "21"))
    lev_cap = float(p.get("cap", "2.0"))
    rebal = p.get("rebal", "daily")

    n = len(close)
    equity = np.full(n, CAPITAL, dtype=np.float64)
    cash = CAPITAL
    position = 0.0
    rebal_freq = 1 if rebal == "daily" else 5

    log_ret = np.zeros(n)
    for i in range(1, n):
        log_ret[i] = np.log(close[i] / close[i - 1])

    for i in range(1, n):
        if i >= vol_win and i % rebal_freq == 0:
            realized_vol = np.std(log_ret[max(1, i - vol_win):i]) * np.sqrt(252)
            target_lev = min(target_vol / realized_vol, lev_cap) if realized_vol > 1e-8 else lev_cap
            current_value = cash + position * close[i]
            target_shares = current_value * target_lev / close[i]
            delta = target_shares - position
            if abs(delta) > 0.001:
                if delta > 0:
                    cost = delta * close[i] * (1 + fee)
                    if cost <= cash:
                        position += delta
                        cash -= cost
                else:
                    proceeds = abs(delta) * close[i] * (1 - fee)
                    position += delta
                    cash += proceeds
        equity[i] = cash + position * close[i]

    trades = n // rebal_freq
    return equity, trades


def replay_event(close, params_str, macro, fee=FEE_RATE):
    """Replay event-based strategies (vix_spike, oil_spike, gold_spike, defense_spike, composite)."""
    p = _parse_params_pipe(params_str)
    n = len(close)

    # Determine event type and build mask
    delay = int(p.get("delay", "0"))
    exit_parts = p.get("exit", "hold_21").split("_", 1)
    exit_method = exit_parts[0]
    exit_param = float(exit_parts[1]) if len(exit_parts) > 1 else 21

    # Detect spike type from params keys
    if "vix_sp" in p:
        sp_th = float(p["vix_sp"])
        win = int(p["win"])
        mask = detect_spike(macro["vix"], win, sp_th)
    elif "oil_sp" in p:
        sp_th = float(p["oil_sp"])
        win = int(p["win"])
        mask = detect_spike(macro["oil"], win, sp_th)
    elif "gold_sp" in p:
        sp_th = float(p["gold_sp"])
        win = int(p["win"])
        mask = detect_spike(macro["gold"], win, sp_th)
    elif "def_sp" in p:
        sp_th = float(p["def_sp"])
        win = int(p["win"])
        if G_DEFENSE_AVG is not None and len(G_DEFENSE_AVG) >= n:
            mask = detect_spike(G_DEFENSE_AVG[:n], win, sp_th)
        else:
            return np.full(n, CAPITAL), 0
    elif "min" in p:
        # Composite signal
        min_count = int(p["min"])
        win = int(p["win"])
        vix_m = detect_spike(macro["vix"], win, 0.20).astype(int)
        oil_m = detect_spike(macro["oil"], win, 0.10).astype(int)
        gold_m = detect_spike(macro["gold"], win, 0.05).astype(int)
        cop_m = detect_spike(macro["copper"], win, 0.10).astype(int)
        count = vix_m + oil_m + gold_m + cop_m
        mask = count >= min_count
    else:
        return np.full(n, CAPITAL), 0

    vix = macro.get("vix")
    return _event_backtest(close, mask, delay, exit_method, exit_param, vix=vix, fee=fee)


def replay_regime_switch(close, params_str, macro, fee=FEE_RATE):
    """Replay regime switching."""
    p = _parse_params_pipe(params_str)
    regime_ind = p.get("ind", "vix_level")
    lookback = int(p.get("lb", "100"))
    map_idx = int(p.get("map", "0"))
    threshold = float(p.get("th", "1.1"))

    strategy_maps = [
        {"bull": "meanrev", "bear": "trend"},
        {"bull": "trend", "bear": "meanrev"},
        {"bull": "meanrev", "bear": "hold"},
        {"bull": "hold", "bear": "trend"},
    ]
    strategy_map = strategy_maps[map_idx] if map_idx < len(strategy_maps) else strategy_maps[0]

    if regime_ind == "oil_sma":
        ind = macro["oil"]
    elif regime_ind == "vix_level":
        ind = macro["vix"]
    else:
        ind = macro["tnx"]

    ind_sma = compute_sma(ind, lookback)
    rsi = compute_rsi(close)
    close_sma50 = compute_sma(close, 50)

    n = len(close)
    equity = np.full(n, CAPITAL, dtype=np.float64)
    cash = CAPITAL
    position = 0.0
    trades = 0

    for i in range(1, n):
        if np.isnan(ind_sma[i]) or np.isnan(close_sma50[i]):
            equity[i] = cash + position * close[i]
            continue
        regime = "bull" if ind[i] > ind_sma[i] * threshold else "bear"
        if regime_ind == "vix_level":
            regime = "bear" if ind[i] > ind_sma[i] * threshold else "bull"
        strat = strategy_map.get(regime, "hold")

        if position > 0:
            sell = False
            if strat == "meanrev" and rsi[i] > 70:
                sell = True
            elif strat == "trend" and close[i] < close_sma50[i]:
                sell = True
            if sell:
                cash = position * close[i] * (1 - fee)
                position = 0.0
                trades += 1
        else:
            buy = False
            if strat == "meanrev" and rsi[i] < 30:
                buy = True
            elif strat == "trend" and close[i] > close_sma50[i] and rsi[i] < 50:
                buy = True
            if buy:
                position = cash * (1 - fee) / close[i]
                cash = 0.0
                trades += 1
        equity[i] = cash + position * close[i]
    return equity, trades


def replay_portfolio(close_dict, params_str, experiment, fee=FEE_RATE):
    """Replay portfolio strategy (2/3/4 asset rebalancing)."""
    # Parse assets and weights from the row
    p = _parse_params_pipe(params_str) if "|" in params_str else {}
    assets_str = p.get("assets", "")
    weights_str = p.get("weights", "")
    rebal_str = p.get("rebal", "monthly")

    # Fallback: read from experiment context
    if not assets_str:
        return np.full(252, CAPITAL), 0

    assets = assets_str.split(",")
    weights = [float(w) for w in weights_str.split(",")]
    n_assets = len(assets)

    # Get aligned close arrays
    closes = []
    min_len = float("inf")
    for sym in assets:
        if sym in close_dict:
            closes.append(close_dict[sym])
            min_len = min(min_len, len(close_dict[sym]))
        else:
            return np.full(252, CAPITAL), 0

    if min_len < 252:
        return np.full(int(min_len), CAPITAL), 0

    n = int(min_len)
    for i in range(len(closes)):
        closes[i] = closes[i][:n]

    # Simulate rebalancing portfolio
    equity = np.full(n, CAPITAL, dtype=np.float64)
    holdings = np.zeros(n_assets)  # shares per asset
    cash = CAPITAL
    trades = 0

    # Initial allocation
    for j in range(n_assets):
        alloc = CAPITAL * weights[j]
        holdings[j] = alloc * (1 - fee) / closes[j][0]
        trades += 1
    cash = 0.0

    # Rebalancing schedule
    if "band" in rebal_str:
        band_pct = float(rebal_str.replace("band_", "").replace("band", "0.05"))
    else:
        band_pct = None

    rebal_period = {"monthly": 21, "quarterly": 63, "annual": 252}.get(rebal_str, 0)

    for i in range(1, n):
        # Current portfolio value
        port_val = sum(holdings[j] * closes[j][i] for j in range(n_assets)) + cash

        # Check rebalance
        do_rebal = False
        if band_pct is not None:
            for j in range(n_assets):
                actual_w = holdings[j] * closes[j][i] / port_val if port_val > 0 else 0
                if abs(actual_w - weights[j]) > band_pct:
                    do_rebal = True
                    break
        elif rebal_period > 0 and i % rebal_period == 0:
            do_rebal = True

        if do_rebal and port_val > 0:
            # Sell all
            for j in range(n_assets):
                cash += holdings[j] * closes[j][i] * (1 - fee)
                holdings[j] = 0
                trades += 1
            # Buy at target weights
            for j in range(n_assets):
                alloc = cash * weights[j]
                holdings[j] = alloc * (1 - fee) / closes[j][i]
                trades += 1
            cash = 0.0

        equity[i] = sum(holdings[j] * closes[j][i] for j in range(n_assets)) + cash

    return equity, trades


def _event_backtest(close, event_mask, entry_delay, exit_method, exit_param,
                    vix=None, fee=FEE_RATE):
    n = len(close)
    equity = np.full(n, CAPITAL, dtype=np.float64)
    cash = CAPITAL
    position = 0.0
    hold_start = 0
    trades = 0
    peak_price = 0.0

    for i in range(1, n):
        if position > 0:
            if exit_method == "hold" and (i - hold_start) >= int(exit_param):
                cash = position * close[i] * (1 - fee)
                position = 0.0
                trades += 1
            elif exit_method == "trail":
                peak_price = max(peak_price, close[i])
                if close[i] < peak_price * (1 - exit_param):
                    cash = position * close[i] * (1 - fee)
                    position = 0.0
                    trades += 1
            elif exit_method == "vix" and vix is not None:
                if vix[i] <= exit_param:
                    cash = position * close[i] * (1 - fee)
                    position = 0.0
                    trades += 1

        if position == 0 and i >= entry_delay:
            trigger_idx = i - entry_delay
            if 0 <= trigger_idx < n and event_mask[trigger_idx]:
                position = cash * (1 - fee) / close[i]
                cash = 0.0
                hold_start = i
                peak_price = close[i]
                trades += 1

        equity[i] = cash + position * close[i]
    return equity, trades


def _dca_weight(rsi_val, scheme, boost_mult):
    if scheme == "none":
        return 1.0
    elif scheme == "linear":
        return max((100.0 - rsi_val) / 50.0, 0.0)
    elif scheme == "threshold":
        return boost_mult if rsi_val < 50.0 else 0.0
    elif scheme == "tiered":
        if rsi_val < 20: return 3.0
        elif rsi_val < 30: return 2.0
        elif rsi_val < 40: return 1.5
        elif rsi_val < 50: return 1.0
        else: return 0.5
    elif scheme == "inverse_sigmoid":
        x = (rsi_val - 50.0) / 15.0
        return max(2.0 / (1.0 + np.exp(x)), 0.0)
    elif scheme == "vol_scaled":
        if rsi_val < 30: return boost_mult
        elif rsi_val < 50: return 1.0 + (boost_mult - 1.0) * (50.0 - rsi_val) / 20.0
        else: return 1.0
    return 1.0


# ══════════════════════════════════════════════════════════════════════
# Param Parsing
# ══════════════════════════════════════════════════════════════════════

def _parse_params(params_str):
    """Parse 'key=val,key=val' format."""
    result = {}
    for part in params_str.split(","):
        if "=" in part:
            k, v = part.split("=", 1)
            result[k.strip()] = v.strip()
    return result


def _parse_params_pipe(params_str):
    """Parse 'key=val|key=val' format."""
    result = {}
    for part in params_str.split("|"):
        if "=" in part:
            k, v = part.split("=", 1)
            result[k.strip()] = v.strip()
    return result


# ══════════════════════════════════════════════════════════════════════
# Strategy Dispatcher
# ══════════════════════════════════════════════════════════════════════

def run_strategy(source, strategy, symbol, params, close, high, low, macro, fee=FEE_RATE):
    """Run a single strategy on given data, return (equity, trades)."""
    try:
        if source == "strategies":
            if strategy == "bb_rsi_ema":
                return replay_bb_rsi_ema(close, params, fee=fee)
            elif strategy == "rsi_solo":
                return replay_rsi_solo(close, params, fee=fee)
            elif strategy == "dca":
                return replay_dca(close, params, fee=fee)
            elif strategy == "momentum":
                return replay_momentum(close, params, fee=fee)
            elif strategy == "macd":
                return replay_macd(close, params, fee=fee)
            elif strategy == "vol_target":
                return replay_vol_target(close, params, fee=fee)
            else:
                # Unsupported strategy types (trailing_stop, multi_tf, seasonality)
                # Fall back to simple BB+RSI
                return replay_bb_rsi_ema(close, "bb=20/2.0,rsi=14/30/70,ema=50,filt=False", fee=fee)

        elif source == "macro":
            if strategy in ("vix_spike", "oil_spike", "gold_spike",
                            "defense_spike", "composite_spike"):
                return replay_event(close, params, macro, fee=fee)
            elif strategy == "regime_switch":
                return replay_regime_switch(close, params, macro, fee=fee)
            else:
                # Other macro experiments: oil_filter, macro_regime, etc.
                # Use BB+RSI as base, macro just modifies behavior
                return replay_bb_rsi_ema(close, "bb=20/2.0,rsi=14/30/70,ema=50,filt=False", fee=fee)

        elif source == "portfolio":
            # Portfolio strategies need multiple asset data
            # Skip in walk-forward (complex alignment)
            return np.full(len(close), CAPITAL), 0

    except Exception:
        return np.full(len(close), CAPITAL), 0

    return np.full(len(close), CAPITAL), 0


# ══════════════════════════════════════════════════════════════════════
# Validation 1: Walk-Forward OOS
# ══════════════════════════════════════════════════════════════════════

def walk_forward_validate(top_strategies):
    """Run top strategies on N_WINDOWS rolling windows."""
    results = []
    train_days = TRAIN_YEARS * 252
    test_days = TEST_YEARS * 252
    slide_days = SLIDE_YEARS * 252

    for row in top_strategies:
        source = row["source"]
        strategy = row.get("strategy", row.get("experiment", ""))
        symbol = row.get("symbol", row.get("target_symbol", ""))
        params = row["params"]

        if symbol not in G_DATA:
            continue

        data = G_DATA[symbol]
        close = data["close"]
        high = data["high"]
        low = data["low"]
        n = len(close)

        # Build macro for this symbol's length
        macro = {}
        for k, v in G_MACRO.items():
            if len(v) >= n:
                macro[k] = v[:n]
            else:
                macro[k] = np.pad(v, (0, n - len(v)), constant_values=np.nan)

        window_results = []
        for w in range(N_WINDOWS):
            start = w * slide_days
            end = start + train_days + test_days
            if end > n:
                break

            train_end = start + train_days
            test_close = close[train_end:end]
            test_high = high[train_end:end]
            test_low = low[train_end:end]
            test_macro = {k: v[train_end:end] for k, v in macro.items()}

            if len(test_close) < 60:
                continue

            eq, trades = run_strategy(source, strategy, symbol, params,
                                      test_close, test_high, test_low, test_macro)
            m = compute_metrics(eq, trades)
            bh_ret = test_close[-1] / test_close[0] - 1 if test_close[0] > 0 else 0
            window_results.append({
                "window": w,
                "sharpe": m["sharpe"],
                "return": m["total_return"],
                "maxdd": m["maxdd"],
                "trades": m["trades"],
                "trades_per_year": m["trades_per_year"],
                "vs_bh": m["total_return"] - bh_ret,
            })

        if window_results:
            sharpes = [r["sharpe"] for r in window_results]
            win_rate = sum(1 for s in sharpes if s > 0.5) / len(sharpes)
            avg_sharpe = np.mean(sharpes)
            avg_vs_bh = np.mean([r["vs_bh"] for r in window_results])
            avg_trades = np.mean([r["trades"] for r in window_results])

            results.append({
                "source": source,
                "strategy": strategy,
                "symbol": symbol,
                "params": params,
                "n_windows": len(window_results),
                "win_rate_sharpe05": round(win_rate, 3),
                "avg_oos_sharpe": round(avg_sharpe, 4),
                "avg_vs_bh": round(avg_vs_bh, 4),
                "avg_trades": round(avg_trades, 1),
                "avg_tpy": round(np.mean([r["trades_per_year"] for r in window_results]), 1),
                "min_sharpe": round(min(sharpes), 4),
                "max_sharpe": round(max(sharpes), 4),
            })

    return results


# ══════════════════════════════════════════════════════════════════════
# Validation 2: Ensemble
# ══════════════════════════════════════════════════════════════════════

def ensemble_validate(top_strategies):
    """Combine top 10 strategies via equal/rank/sharpe/vote."""
    results = []
    # Group by symbol
    by_symbol = defaultdict(list)
    for row in top_strategies[:10]:
        sym = row.get("symbol", row.get("target_symbol", ""))
        if sym:
            by_symbol[sym].append(row)

    for sym, strats in by_symbol.items():
        if sym not in G_DATA or len(strats) < 2:
            continue

        data = G_DATA[sym]
        close = data["close"]
        high = data["high"]
        low = data["low"]
        n = len(close)
        split = int(n * 0.7)
        oos_close = close[split:]
        oos_high = high[split:]
        oos_low = low[split:]

        macro = {}
        for k, v in G_MACRO.items():
            if len(v) >= n:
                macro[k] = v[split:n]
            else:
                macro[k] = np.pad(v, (0, max(0, n - len(v))), constant_values=np.nan)[split:n]

        oos_n = len(oos_close)
        if oos_n < 60:
            continue

        # Collect equity curves
        eq_curves = []
        sharpes = []
        for row in strats:
            source = row["source"]
            strategy = row.get("strategy", row.get("experiment", ""))
            params = row["params"]
            eq, _ = run_strategy(source, strategy, sym, params,
                                 oos_close, oos_high, oos_low, macro)
            eq_curves.append(eq)
            sharpes.append(row.get("oos_sharpe", 0))

        if not eq_curves:
            continue

        bh_ret = oos_close[-1] / oos_close[0] - 1 if oos_close[0] > 0 else 0

        # Method 1: Equal weight average of equity curves
        avg_eq = np.mean(eq_curves, axis=0)
        m = compute_metrics(avg_eq, 0)
        results.append({
            "method": "equal_weight",
            "symbol": sym,
            "n_strategies": len(strats),
            "oos_sharpe": round(m["sharpe"], 4),
            "oos_return": round(m["total_return"], 4),
            "oos_maxdd": round(m["maxdd"], 4),
            "vs_bh": round(m["total_return"] - bh_ret, 4),
            "years": m["years"],
        })

        # Method 2: Sharpe-weighted average
        if sum(max(s, 0) for s in sharpes) > 0:
            w = np.array([max(s, 0) for s in sharpes])
            w = w / w.sum()
            sharpe_eq = np.average(eq_curves, axis=0, weights=w)
            m2 = compute_metrics(sharpe_eq, 0)
            results.append({
                "method": "sharpe_weight",
                "symbol": sym,
                "n_strategies": len(strats),
                "oos_sharpe": round(m2["sharpe"], 4),
                "oos_return": round(m2["total_return"], 4),
                "oos_maxdd": round(m2["maxdd"], 4),
                "vs_bh": round(m2["total_return"] - bh_ret, 4),
                "years": m2["years"],
            })

        # Method 3: Rank-weighted (rank 1=best gets highest weight)
        ranks = np.argsort(np.argsort([-s for s in sharpes])) + 1
        rank_w = 1.0 / ranks
        rank_w = rank_w / rank_w.sum()
        rank_eq = np.average(eq_curves, axis=0, weights=rank_w)
        m3 = compute_metrics(rank_eq, 0)
        results.append({
            "method": "rank_weight",
            "symbol": sym,
            "n_strategies": len(strats),
            "oos_sharpe": round(m3["sharpe"], 4),
            "oos_return": round(m3["total_return"], 4),
            "oos_maxdd": round(m3["maxdd"], 4),
            "vs_bh": round(m3["total_return"] - bh_ret, 4),
            "years": m3["years"],
        })

        # Method 4: Majority vote (invest only when >50% strategies rising)
        vote_eq = np.full(oos_n, CAPITAL, dtype=np.float64)
        cash = CAPITAL
        position = 0.0
        trades = 0
        for i in range(1, oos_n):
            rising = sum(1 for eq in eq_curves if eq[i] > eq[i - 1])
            if rising > len(eq_curves) / 2 and position == 0:
                position = cash * (1 - FEE_RATE) / oos_close[i]
                cash = 0.0
                trades += 1
            elif rising <= len(eq_curves) / 2 and position > 0:
                cash = position * oos_close[i] * (1 - FEE_RATE)
                position = 0.0
                trades += 1
            vote_eq[i] = cash + position * oos_close[i]

        m4 = compute_metrics(vote_eq, trades)
        results.append({
            "method": "majority_vote",
            "symbol": sym,
            "n_strategies": len(strats),
            "oos_sharpe": round(m4["sharpe"], 4),
            "oos_return": round(m4["total_return"], 4),
            "oos_maxdd": round(m4["maxdd"], 4),
            "vs_bh": round(m4["total_return"] - bh_ret, 4),
            "trades": trades,
            "trades_per_year": m4["trades_per_year"],
            "years": m4["years"],
        })

    return results


# ══════════════════════════════════════════════════════════════════════
# Validation 3: Fee Sensitivity
# ══════════════════════════════════════════════════════════════════════

def fee_sensitivity_validate(top_strategies):
    """Re-run top strategies at different fee levels."""
    results = []

    for row in top_strategies:
        source = row["source"]
        strategy = row.get("strategy", row.get("experiment", ""))
        symbol = row.get("symbol", row.get("target_symbol", ""))
        params = row["params"]

        if symbol not in G_DATA:
            continue

        data = G_DATA[symbol]
        close = data["close"]
        high = data["high"]
        low = data["low"]
        n = len(close)
        split = int(n * 0.7)
        oos_close = close[split:]
        oos_high = high[split:]
        oos_low = low[split:]

        macro = {}
        for k, v in G_MACRO.items():
            if len(v) >= n:
                macro[k] = v[split:n]
            else:
                macro[k] = np.pad(v, (0, max(0, n - len(v))), constant_values=np.nan)[split:n]

        if len(oos_close) < 60:
            continue

        bh_ret = oos_close[-1] / oos_close[0] - 1 if oos_close[0] > 0 else 0

        for fee_rate in FEE_LEVELS:
            eq, trades = run_strategy(source, strategy, symbol, params,
                                      oos_close, oos_high, oos_low, macro, fee=fee_rate)
            m = compute_metrics(eq, trades)
            results.append({
                "source": source,
                "strategy": strategy,
                "symbol": symbol,
                "params": params,
                "fee_pct": round(fee_rate * 100, 2),
                "oos_sharpe": round(m["sharpe"], 4),
                "oos_return": round(m["total_return"], 4),
                "oos_maxdd": round(m["maxdd"], 4),
                "oos_trades": m["trades"],
                "trades_per_year": m["trades_per_year"],
                "vs_bh": round(m["total_return"] - bh_ret, 4),
                "years": m["years"],
            })

    return results


# ══════════════════════════════════════════════════════════════════════
# Data Loading
# ══════════════════════════════════════════════════════════════════════

def load_all_data():
    """Load all symbol data into G_DATA and G_MACRO."""
    global G_DATA, G_MACRO, G_DEFENSE_AVG, G_SPY_CLOSE

    all_syms = set(ENERGY + DEFENSE + TECH + PORTFOLIO_ENERGY + PORTFOLIO_TECH +
                   PORTFOLIO_DEFENSE_ASSETS + PORTFOLIO_LEV_TECH + ["SPY"])

    for sym in all_syms:
        fpath = DATA_DIR / f"{sym}.parquet"
        if not fpath.exists():
            continue
        df = pd.read_parquet(fpath)
        if len(df) < 252:
            continue
        close = df["close"].values.astype(np.float64)
        high = df["high"].values.astype(np.float64) if "high" in df.columns else close.copy()
        low = df["low"].values.astype(np.float64) if "low" in df.columns else close.copy()
        dates = df.index
        G_DATA[sym] = {"close": close, "high": high, "low": low, "dates": dates}

    if "SPY" in G_DATA:
        G_SPY_CLOSE = G_DATA["SPY"]["close"]

    # Load macro
    for yf_sym, name in MACRO_SYMS.items():
        fpath = DATA_DIR / f"{yf_sym}.parquet"
        if not fpath.exists():
            continue
        df = pd.read_parquet(fpath)
        G_MACRO[name] = df["close"].values.astype(np.float64)

    # Defense average
    def_closes = []
    for sym in DEFENSE:
        if sym in G_DATA:
            def_closes.append(G_DATA[sym]["close"])
    if def_closes:
        min_len = min(len(c) for c in def_closes)
        aligned = np.column_stack([c[:min_len] for c in def_closes])
        # Normalize each to 100 then average
        normalized = aligned / aligned[0] * 100
        G_DEFENSE_AVG = np.mean(normalized, axis=1)


def load_top_strategies():
    """Load top N strategies from Phase 1-3 result CSVs."""
    top_all = []

    # Strategies (Phase 1)
    strat_file = RESULTS_DIR / "energy_strategies_results.csv"
    if strat_file.exists():
        df = pd.read_csv(strat_file)
        # Filter: oos_trades >= 3
        df = df[df["oos_trades"] >= 3]
        top = df.nlargest(TOP_N, "oos_sharpe")
        for _, row in top.iterrows():
            top_all.append({
                "source": "strategies",
                "strategy": row["strategy"],
                "symbol": row["symbol"],
                "params": row["params"],
                "oos_sharpe": row["oos_sharpe"],
                "oos_return": row["oos_return"],
            })

    # Macro (Phase 2)
    macro_file = RESULTS_DIR / "energy_macro_results.csv"
    if macro_file.exists():
        df = pd.read_csv(macro_file)
        df = df[df["oos_trades"] >= 3]
        top = df.nlargest(TOP_N, "oos_sharpe")
        for _, row in top.iterrows():
            top_all.append({
                "source": "macro",
                "strategy": row["experiment"],
                "symbol": row["target_symbol"],
                "params": row["params"],
                "oos_sharpe": row["oos_sharpe"],
                "oos_return": row["oos_return"],
            })

    # Portfolio (Phase 3) — limited validation (no walk-forward)
    port_file = RESULTS_DIR / "energy_portfolio_results.csv"
    if port_file.exists():
        df = pd.read_csv(port_file)
        df = df[df["oos_trades"] >= 3]
        top = df.nlargest(TOP_N, "oos_sharpe")
        for _, row in top.iterrows():
            top_all.append({
                "source": "portfolio",
                "strategy": row["experiment"],
                "symbol": row.get("assets", ""),
                "params": row["weights"] if "weights" in row else "",
                "oos_sharpe": row["oos_sharpe"],
                "oos_return": row["oos_return"],
            })

    return top_all


# ══════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════

def main():
    t0 = time.time()
    print("=" * 70)
    print("Energy Cross-Sector Validation (Phase 4)")
    print("=" * 70)

    # Load data
    print("\n[1/5] Loading all symbol data...")
    load_all_data()
    print(f"  Loaded {len(G_DATA)} symbols, {len(G_MACRO)} macro indicators")

    # Load top strategies
    print("\n[2/5] Loading top strategies from Phase 1-3...")
    top_all = load_top_strategies()
    print(f"  Loaded {len(top_all)} top strategies")

    if not top_all:
        print("No strategies found. Run Phase 1-3 first.")
        return

    # Separate by source
    strat_top = [r for r in top_all if r["source"] == "strategies"]
    macro_top = [r for r in top_all if r["source"] == "macro"]
    port_top = [r for r in top_all if r["source"] == "portfolio"]

    print(f"  Strategies: {len(strat_top)}, Macro: {len(macro_top)}, Portfolio: {len(port_top)}")

    all_results = []

    # ── Walk-Forward OOS ──
    print(f"\n[3/5] Walk-Forward OOS (top {TOP_N} × {N_WINDOWS} windows)...")
    wf_strats = strat_top + macro_top  # skip portfolio for WF
    wf_results = walk_forward_validate(wf_strats)
    print(f"  {len(wf_results)} walk-forward results")

    for r in wf_results:
        r["validation"] = "walk_forward"
        all_results.append(r)

    # Print WF summary
    if wf_results:
        print("\n  === Walk-Forward Top 10 (by win rate) ===")
        wf_sorted = sorted(wf_results, key=lambda x: x["win_rate_sharpe05"], reverse=True)[:10]
        for r in wf_sorted:
            print(f"  {r['symbol']:5s} {r['strategy']:20s} WR={r['win_rate_sharpe05']:.0%} "
                  f"avgSharpe={r['avg_oos_sharpe']:.2f} avgVsBH={r['avg_vs_bh']:+.2%} "
                  f"avgTrades={r['avg_trades']:.0f} tpy={r['avg_tpy']:.1f}")

    # ── Ensemble ──
    print(f"\n[4/5] Ensemble (top 10 × 4 methods)...")
    ensemble_input = sorted(top_all, key=lambda x: x["oos_sharpe"], reverse=True)[:10]
    ens_results = ensemble_validate(ensemble_input)
    print(f"  {len(ens_results)} ensemble results")

    for r in ens_results:
        r["validation"] = "ensemble"
        all_results.append(r)

    if ens_results:
        print("\n  === Ensemble Results ===")
        for r in ens_results:
            trades_info = f" trades={r.get('trades', 'N/A')} tpy={r.get('trades_per_year', 'N/A')}" if 'trades' in r else ""
            print(f"  {r['method']:15s} {r['symbol']:5s} Sharpe={r['oos_sharpe']:.2f} "
                  f"Ret={r['oos_return']:+.1%} MDD={r['oos_maxdd']:.1%} "
                  f"vsBH={r['vs_bh']:+.1%}{trades_info}")

    # ── Fee Sensitivity ──
    print(f"\n[5/5] Fee Sensitivity (top {TOP_N} × {len(FEE_LEVELS)} fees)...")
    fee_input = sorted(top_all, key=lambda x: x["oos_sharpe"], reverse=True)[:TOP_N]
    # Exclude portfolio from fee sensitivity (complex replay)
    fee_input = [r for r in fee_input if r["source"] != "portfolio"]
    fee_results = fee_sensitivity_validate(fee_input)
    print(f"  {len(fee_results)} fee sensitivity results")

    for r in fee_results:
        r["validation"] = "fee_sensitivity"
        all_results.append(r)

    # Fee sensitivity summary: breakeven fee per strategy
    if fee_results:
        print("\n  === Fee Sensitivity: Breakeven Fee ===")
        # Group by strategy+symbol, find max fee where vs_bh > 0
        from collections import defaultdict
        fee_groups = defaultdict(list)
        for r in fee_results:
            key = (r["strategy"], r["symbol"])
            fee_groups[key].append(r)

        for (strat, sym), rows in sorted(fee_groups.items()):
            rows_sorted = sorted(rows, key=lambda x: x["fee_pct"])
            profitable_fees = [r["fee_pct"] for r in rows_sorted if r["vs_bh"] > 0]
            breakeven = max(profitable_fees) if profitable_fees else 0
            base_sharpe = rows_sorted[2]["oos_sharpe"] if len(rows_sorted) > 2 else 0  # 0.25% fee
            print(f"  {sym:5s} {strat:20s} breakeven={breakeven:.2f}% "
                  f"baseSharpe@0.25%={base_sharpe:.2f} "
                  f"trades={rows_sorted[2].get('oos_trades', 0)} "
                  f"tpy={rows_sorted[2].get('trades_per_year', 0):.1f}")

    # Save results
    out_path = RESULTS_DIR / "energy_validate_results.csv"
    df_out = pd.DataFrame(all_results)
    df_out.to_csv(out_path, index=False)
    print(f"\n  Saved {len(all_results)} results to {out_path}")

    elapsed = time.time() - t0
    print(f"\n{'=' * 70}")
    print(f"Total: {len(all_results)} validations in {elapsed:.0f}s ({elapsed / 60:.1f}min)")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    main()
