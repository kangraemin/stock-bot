"""Experiment: Energy Macro/Event Filter Backtests (~17,500 combinations)

Self-contained numpy-based backtester.
Macro filters (oil, gas, VIX, rates, dollar, copper, gold) applied to energy/defense/tech.
Geopolitical event proxy via spike detection.
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

# -- Constants --
PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
RESULTS_DIR = PROJECT_ROOT / "results"
RESULTS_DIR.mkdir(exist_ok=True)

CAPITAL = 2000.0
FEE_RATE = 0.0025
IS_RATIO = 0.70

# -- Symbols --
ENERGY = ["CVX", "XOM", "XLE", "XOP", "OIH", "FANG", "VDE", "ERX",
          "COP", "SLB", "EOG", "MPC", "PSX", "HAL", "DVN"]
DEFENSE = ["LMT", "RTX", "NOC"]
TECH = ["NVDA", "AAPL", "MSFT"]
ALL_TARGETS = ENERGY + DEFENSE + TECH  # 21

DIVIDEND_SYMS = ["CVX", "XOM", "COP", "PSX", "MPC", "EOG"]

MACRO_SYMS = {
    "CL=F": "oil", "NG=F": "natgas", "^VIX": "vix",
    "GC=F": "gold", "^TNX": "tnx", "DX-Y.NYB": "dxy", "HG=F": "copper",
}

# -- Experiment grids --
# 1. Oil filter (600)
OIL_MA = [10, 20, 50, 100, 200]
OIL_STRATEGY = ["block", "boost", "adjust", "force_sell", "half"]
OIL_SENSITIVITY = [0.9, 0.95, 1.0, 1.05]
OIL_CONFIRM = [1, 3, 5]
OIL_RSI_BUY = [25, 35]

# 2. Natgas spike (36)
GAS_SPIKE = [0.05, 0.10, 0.15]
GAS_SPIKE_WINDOW = [1, 3, 5]
GAS_ACTION = ["buy_energy", "sell_energy", "hedge_gold", "hold"]

# 3. Oil+Gas combined (45)
REGIME_VALS = ["up", "down", "flat"]
OILGAS_STRATEGY = ["buy", "sell", "hedge", "rotate", "hold"]

# 4. Dividend B&H (12)
DIV_REINVEST = [True, False]
DIV_TAX = [0.0, 0.15]

# 5. Macro regime (1600)
MACRO_INDICATORS = ["vix", "tnx", "dxy", "copper"]
MACRO_LOOKBACK = [20, 50, 100, 200]
MACRO_THRESHOLD = [0.9, 0.95, 1.05, 1.1]
MACRO_ACTION = ["block", "adjust", "force", "half"]
MACRO_CONFIRM = [1, 3, 5, 10]

# 6. Regime switching (144)
REGIME_IND = ["oil_sma", "vix_level", "tnx_direction"]
REGIME_LOOKBACK = [50, 100, 200]
REGIME_STRATEGY_MAP = [
    {"bull": "meanrev", "bear": "trend"},
    {"bull": "trend", "bear": "meanrev"},
    {"bull": "meanrev", "bear": "hold"},
    {"bull": "hold", "bear": "trend"},
]
REGIME_THRESHOLD = [0.9, 0.95, 1.05, 1.1]

# 7-11. Event proxy
VIX_SPIKE_THRESH = [0.10, 0.15, 0.20, 0.30, 0.40, 0.50]
SPIKE_WIN = [1, 2, 3, 5]
ENTRY_DELAY = [0, 1, 2, 3, 5]
EXIT_METHODS = [
    ("hold", 5), ("hold", 10), ("hold", 21), ("hold", 42),
    ("hold", 60), ("hold", 120),
    ("trail", 0.05), ("trail", 0.10), ("trail", 0.15), ("trail", 0.20),
    ("vix_norm", 20), ("vix_norm", 22), ("vix_norm", 25),
]

OIL_SPIKE_THRESH = [0.05, 0.10, 0.15, 0.20, 0.30]
GOLD_SPIKE_THRESH = [0.03, 0.05, 0.08, 0.10, 0.15]
DEFENSE_SPIKE_THRESH = [0.05, 0.10, 0.15, 0.20]

COMPOSITE_MIN = [2, 3, 4]

# 12. Beta filter (50 after pruning -> ~20 per target subset)
BETA_WIN = [21, 63, 126, 252]
BETA_THRESH = [0.5, 0.8, 1.0, 1.2, 1.5]

# -- Global data (populated in main, inherited by fork) --
G_DATA = {}  # target_sym -> {close, dates, macro: {oil, natgas, vix, gold, tnx, dxy, copper}}
G_DEFENSE_AVG = None  # defense average close array
G_SPY_CLOSE = None  # SPY close for beta calc


# -- Helpers --
def compute_rsi(close, period=14):
    """Compute RSI from close prices."""
    delta = np.diff(close)
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)
    avg_gain = np.zeros(len(close))
    avg_loss = np.zeros(len(close))
    if len(gain) < period:
        return np.full(len(close), 50.0)
    avg_gain[period] = np.mean(gain[:period])
    avg_loss[period] = np.mean(loss[:period])
    for i in range(period + 1, len(close)):
        avg_gain[i] = (avg_gain[i - 1] * (period - 1) + gain[i - 1]) / period
        avg_loss[i] = (avg_loss[i - 1] * (period - 1) + loss[i - 1]) / period
    rs = np.where(avg_loss > 0, avg_gain / avg_loss, 100.0)
    rsi = 100.0 - 100.0 / (1.0 + rs)
    rsi[:period] = 50.0
    return rsi


def compute_sma(arr, window):
    """Simple moving average."""
    out = np.full(len(arr), np.nan)
    if len(arr) < window:
        return out
    cs = np.cumsum(arr)
    out[window - 1:] = (cs[window - 1:] - np.concatenate([[0], cs[:-window]])) / window
    return out


def detect_spike(series, lookback, threshold):
    """Detect spike: series moved > threshold pct vs lookback periods ago."""
    mask = np.zeros(len(series), dtype=bool)
    if len(series) <= lookback:
        return mask
    pct = series[lookback:] / series[:-lookback] - 1.0
    mask[lookback:] = pct > threshold
    return mask


def compute_metrics(equity, n_days, trades):
    """Compute backtest metrics from equity curve."""
    if n_days < 2 or equity[0] <= 0:
        return None
    initial, final = equity[0], equity[n_days - 1]
    total_return = (final - initial) / initial
    yrs = n_days / 252.0
    if yrs <= 0:
        return None
    ann_ret = (final / initial) ** (1.0 / yrs) - 1.0
    peak = np.maximum.accumulate(equity[:n_days])
    dd = (equity[:n_days] - peak) / peak
    max_dd = float(np.min(dd))
    dr = np.diff(equity[:n_days]) / equity[:n_days - 1]
    std = np.std(dr, ddof=1) if len(dr) > 1 else 0.0
    sharpe = float(np.mean(dr) / std * np.sqrt(252)) if std > 0 else 0.0
    calmar = ann_ret / abs(max_dd) if max_dd != 0 else 0.0
    return {
        "total_return": total_return,
        "sharpe": sharpe,
        "maxdd": max_dd,
        "calmar": calmar,
        "trades": trades,
        "years": round(yrs, 2),
        "trades_per_year": round(trades / yrs, 1) if yrs > 0 else 0,
    }


def bh_return(close):
    """Buy & hold return."""
    if len(close) < 2 or close[0] <= 0:
        return 0.0
    shares = CAPITAL * (1 - FEE_RATE) / close[0]
    final = shares * close[-1] * (1 - FEE_RATE)
    return (final - CAPITAL) / CAPITAL


# -- Experiment backtests --

def bb_rsi_backtest(close, rsi_buy=30, rsi_sell=70, bb_period=20, bb_std=2.0):
    """Simple BB+RSI mean-reversion backtest."""
    n = len(close)
    equity = np.full(n, CAPITAL, dtype=np.float64)
    cash = CAPITAL
    position = 0.0
    trades = 0
    rsi = compute_rsi(close)
    sma = compute_sma(close, bb_period)
    std = np.full(n, np.nan)
    for i in range(bb_period - 1, n):
        std[i] = np.std(close[i - bb_period + 1:i + 1], ddof=0)
    lower = sma - bb_std * std
    upper = sma + bb_std * std

    for i in range(1, n):
        if position > 0:
            if rsi[i] > rsi_sell and not np.isnan(upper[i]) and close[i] > upper[i]:
                cash = position * close[i] * (1 - FEE_RATE)
                position = 0.0
                trades += 1
        else:
            if rsi[i] < rsi_buy and not np.isnan(lower[i]) and close[i] < lower[i]:
                position = cash * (1 - FEE_RATE) / close[i]
                cash = 0.0
                trades += 1
        equity[i] = cash + position * close[i]
    return equity, trades


def exp1_oil_filter(close, macro, rsi_buy, ma_period, strategy, sensitivity, confirm):
    """Exp1: Oil SMA filter on BB+RSI strategy."""
    oil = macro["oil"]
    n = len(close)
    oil_sma = compute_sma(oil, ma_period)
    oil_above = np.zeros(n, dtype=np.int32)
    for i in range(1, n):
        if not np.isnan(oil_sma[i]):
            if oil[i] > oil_sma[i] * sensitivity:
                oil_above[i] = oil_above[i - 1] + 1
            elif oil[i] < oil_sma[i] * (2.0 - sensitivity):
                oil_above[i] = -(abs(oil_above[i - 1]) + 1) if oil_above[i - 1] <= 0 else -1
            else:
                oil_above[i] = 0

    rsi = compute_rsi(close)
    sma20 = compute_sma(close, 20)
    std20 = np.full(n, np.nan)
    for i in range(19, n):
        std20[i] = np.std(close[i - 19:i + 1], ddof=0)
    lower = sma20 - 2.0 * std20
    upper = sma20 + 2.0 * std20

    equity = np.full(n, CAPITAL, dtype=np.float64)
    cash = CAPITAL
    position = 0.0
    trades = 0

    for i in range(1, n):
        oil_bull = oil_above[i] >= confirm
        oil_bear = oil_above[i] <= -confirm

        if position > 0:
            # Sell logic
            sell = False
            if rsi[i] > 70 and not np.isnan(upper[i]) and close[i] > upper[i]:
                sell = True
            if strategy == "force_sell" and oil_bear:
                sell = True
            if sell:
                cash = position * close[i] * (1 - FEE_RATE)
                position = 0.0
                trades += 1
        else:
            # Buy logic
            effective_rsi_buy = rsi_buy
            can_buy = True

            if strategy == "block" and oil_bear:
                can_buy = False
            elif strategy == "boost" and oil_bull:
                effective_rsi_buy = min(rsi_buy + 10, 50)  # easier buy
            elif strategy == "adjust":
                if oil_bull:
                    effective_rsi_buy = min(rsi_buy + 5, 50)
                elif oil_bear:
                    effective_rsi_buy = max(rsi_buy - 5, 10)
            elif strategy == "half":
                pass  # handled below

            if can_buy and rsi[i] < effective_rsi_buy and not np.isnan(lower[i]) and close[i] < lower[i]:
                if strategy == "half" and oil_bear:
                    alloc = cash * 0.5
                else:
                    alloc = cash
                position = alloc * (1 - FEE_RATE) / close[i]
                cash -= alloc
                trades += 1

        equity[i] = cash + position * close[i]
    return equity, trades


def exp2_gas_spike(close, macro, spike_pct, spike_win, action):
    """Exp2: Natural gas spike filter."""
    gas = macro["natgas"]
    gold = macro["gold"]
    n = len(close)
    gas_spike_mask = detect_spike(gas, spike_win, spike_pct)

    equity = np.full(n, CAPITAL, dtype=np.float64)
    cash = CAPITAL
    position = 0.0
    trades = 0
    in_gold = False
    gold_shares = 0.0

    for i in range(1, n):
        if gas_spike_mask[i]:
            if action == "buy_energy" and position == 0:
                position = cash * (1 - FEE_RATE) / close[i]
                cash = 0.0
                trades += 1
            elif action == "sell_energy" and position > 0:
                cash = position * close[i] * (1 - FEE_RATE)
                position = 0.0
                trades += 1
            elif action == "hedge_gold" and not in_gold and cash > 0:
                gold_shares = (cash * 0.5) * (1 - FEE_RATE) / gold[i]
                cash *= 0.5
                in_gold = True
                trades += 1
        else:
            if in_gold and gold_shares > 0:
                cash += gold_shares * gold[i] * (1 - FEE_RATE)
                gold_shares = 0.0
                in_gold = False
                trades += 1

        equity[i] = cash + position * close[i] + gold_shares * gold[i]
    return equity, trades


def exp3_oil_gas_regime(close, macro, oil_regime, gas_regime, strategy):
    """Exp3: Combined oil+gas regime."""
    oil = macro["oil"]
    gas = macro["natgas"]
    gold = macro["gold"]
    n = len(close)
    oil_sma50 = compute_sma(oil, 50)
    gas_sma50 = compute_sma(gas, 50)

    equity = np.full(n, CAPITAL, dtype=np.float64)
    cash = CAPITAL
    position = 0.0
    trades = 0
    rsi = compute_rsi(close)

    for i in range(1, n):
        if np.isnan(oil_sma50[i]) or np.isnan(gas_sma50[i]):
            equity[i] = cash + position * close[i]
            continue

        # Determine current regimes
        cur_oil = "up" if oil[i] > oil_sma50[i] * 1.02 else ("down" if oil[i] < oil_sma50[i] * 0.98 else "flat")
        cur_gas = "up" if gas[i] > gas_sma50[i] * 1.02 else ("down" if gas[i] < gas_sma50[i] * 0.98 else "flat")

        regime_match = (cur_oil == oil_regime) and (cur_gas == gas_regime)

        if position > 0:
            if rsi[i] > 70 or (not regime_match and strategy in ("buy", "rotate")):
                cash = position * close[i] * (1 - FEE_RATE)
                position = 0.0
                trades += 1
        else:
            if regime_match and rsi[i] < 35:
                if strategy in ("buy", "rotate"):
                    position = cash * (1 - FEE_RATE) / close[i]
                    cash = 0.0
                    trades += 1
                elif strategy == "hedge":
                    position = cash * 0.5 * (1 - FEE_RATE) / close[i]
                    cash *= 0.5
                    trades += 1

        equity[i] = cash + position * close[i]
    return equity, trades


def exp4_dividend_bh(close, reinvest, tax_rate):
    """Exp4: Dividend B&H with reinvestment option."""
    n = len(close)
    # Approximate quarterly dividend: ~3% annual yield -> 0.75% per quarter
    div_yield_q = 0.0075
    equity = np.full(n, CAPITAL, dtype=np.float64)
    shares = CAPITAL * (1 - FEE_RATE) / close[0]
    cash = 0.0
    trades = 1
    quarter_days = 63  # approx trading days per quarter

    for i in range(1, n):
        if i % quarter_days == 0 and i > 0:
            div_per_share = close[i] * div_yield_q
            div_total = shares * div_per_share * (1 - tax_rate)
            if reinvest:
                new_shares = div_total * (1 - FEE_RATE) / close[i]
                shares += new_shares
                trades += 1
            else:
                cash += div_total
        equity[i] = shares * close[i] + cash
    return equity, trades


def exp5_macro_regime(close, macro, indicator, lookback, threshold, action, confirm):
    """Exp5: Single macro indicator regime filter."""
    ind_data = macro[indicator]
    n = len(close)
    ind_sma = compute_sma(ind_data, lookback)
    rsi = compute_rsi(close)

    sma20 = compute_sma(close, 20)
    std20 = np.full(n, np.nan)
    for i in range(19, n):
        std20[i] = np.std(close[i - 19:i + 1], ddof=0)
    lower = sma20 - 2.0 * std20
    upper = sma20 + 2.0 * std20

    equity = np.full(n, CAPITAL, dtype=np.float64)
    cash = CAPITAL
    position = 0.0
    trades = 0
    above_count = 0

    for i in range(1, n):
        if not np.isnan(ind_sma[i]):
            if ind_data[i] > ind_sma[i] * threshold:
                above_count = max(above_count + 1, 1)
            elif ind_data[i] < ind_sma[i] * (2.0 - threshold):
                above_count = min(above_count - 1, -1)
            else:
                above_count = 0

        macro_high = above_count >= confirm
        macro_low = above_count <= -confirm

        # For VIX, high = risk-off; for others, interpret differently
        is_risk_off = macro_high if indicator == "vix" else macro_low

        if position > 0:
            sell = False
            if rsi[i] > 70 and not np.isnan(upper[i]) and close[i] > upper[i]:
                sell = True
            if action == "force" and is_risk_off:
                sell = True
            if sell:
                cash = position * close[i] * (1 - FEE_RATE)
                position = 0.0
                trades += 1
        else:
            can_buy = True
            rsi_thresh = 30

            if action == "block" and is_risk_off:
                can_buy = False
            elif action == "adjust":
                if is_risk_off:
                    rsi_thresh = 20  # stricter
                else:
                    rsi_thresh = 40  # easier
            elif action == "half":
                pass

            if can_buy and rsi[i] < rsi_thresh and not np.isnan(lower[i]) and close[i] < lower[i]:
                if action == "half" and is_risk_off:
                    alloc = cash * 0.5
                else:
                    alloc = cash
                position = alloc * (1 - FEE_RATE) / close[i]
                cash -= alloc
                trades += 1

        equity[i] = cash + position * close[i]
    return equity, trades


def exp6_regime_switch(close, macro, regime_ind, lookback, strategy_map, threshold):
    """Exp6: Regime switching between MeanRev and TrendFollow."""
    n = len(close)
    if regime_ind == "oil_sma":
        ind = macro["oil"]
    elif regime_ind == "vix_level":
        ind = macro["vix"]
    else:  # tnx_direction
        ind = macro["tnx"]

    ind_sma = compute_sma(ind, lookback)
    rsi = compute_rsi(close)
    close_sma50 = compute_sma(close, 50)

    equity = np.full(n, CAPITAL, dtype=np.float64)
    cash = CAPITAL
    position = 0.0
    trades = 0

    for i in range(1, n):
        if np.isnan(ind_sma[i]) or np.isnan(close_sma50[i]):
            equity[i] = cash + position * close[i]
            continue

        regime = "bull" if ind[i] > ind_sma[i] * threshold else "bear"
        # For VIX, invert: high VIX = bear
        if regime_ind == "vix_level":
            regime = "bear" if ind[i] > ind_sma[i] * threshold else "bull"

        strat = strategy_map.get(regime, "hold")

        if position > 0:
            sell = False
            if strat == "meanrev" and rsi[i] > 70:
                sell = True
            elif strat == "trend" and close[i] < close_sma50[i]:
                sell = True
            elif strat == "hold":
                pass  # hold through
            if sell:
                cash = position * close[i] * (1 - FEE_RATE)
                position = 0.0
                trades += 1
        else:
            buy = False
            if strat == "meanrev" and rsi[i] < 30:
                buy = True
            elif strat == "trend" and close[i] > close_sma50[i] and rsi[i] < 50:
                buy = True
            if buy:
                position = cash * (1 - FEE_RATE) / close[i]
                cash = 0.0
                trades += 1

        equity[i] = cash + position * close[i]
    return equity, trades


def event_backtest(close, event_mask, entry_delay, exit_method, exit_param,
                   vix=None, capital=CAPITAL, fee=FEE_RATE):
    """Event-driven backtest: spike -> delay -> buy -> exit."""
    n = len(close)
    equity = np.full(n, capital, dtype=np.float64)
    cash = capital
    position = 0.0
    entry_price = 0.0
    hold_start = 0
    trades = 0
    peak_price = 0.0

    for i in range(1, n):
        # Sell check
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
            elif exit_method == "vix_norm" and vix is not None:
                if vix[i] <= exit_param:
                    cash = position * close[i] * (1 - fee)
                    position = 0.0
                    trades += 1

        # Buy check
        if position == 0 and i >= entry_delay:
            trigger_idx = i - entry_delay
            if 0 <= trigger_idx < n and event_mask[trigger_idx]:
                position = cash * (1 - fee) / close[i]
                cash = 0.0
                entry_price = close[i]
                hold_start = i
                peak_price = close[i]
                trades += 1

        equity[i] = cash + position * close[i]

    return equity, trades


def exp12_beta_filter(close, spy_close, beta_win, beta_thresh):
    """Exp12: Buy when rolling beta vs SPY is below threshold."""
    n = len(close)
    rsi = compute_rsi(close)

    equity = np.full(n, CAPITAL, dtype=np.float64)
    cash = CAPITAL
    position = 0.0
    trades = 0

    # Precompute rolling beta
    ret_sym = np.diff(close) / close[:-1]
    ret_spy = np.diff(spy_close) / spy_close[:-1]
    betas = np.full(n, 1.0)
    for i in range(beta_win, len(ret_sym)):
        rs = ret_sym[i - beta_win:i]
        rm = ret_spy[i - beta_win:i]
        cov = np.cov(rs, rm)
        if cov.shape == (2, 2) and cov[1, 1] > 0:
            betas[i + 1] = cov[0, 1] / cov[1, 1]

    for i in range(1, n):
        if position > 0:
            if rsi[i] > 70 or betas[i] > beta_thresh * 1.5:
                cash = position * close[i] * (1 - FEE_RATE)
                position = 0.0
                trades += 1
        else:
            if betas[i] < beta_thresh and rsi[i] < 35:
                position = cash * (1 - FEE_RATE) / close[i]
                cash = 0.0
                trades += 1

        equity[i] = cash + position * close[i]
    return equity, trades


# -- Worker --
def process_target(target_sym):
    """Process all 12 experiments for one target symbol."""
    data = G_DATA[target_sym]
    close = data["close"]
    macro = data["macro"]
    n_total = len(close)
    split = int(n_total * IS_RATIO)
    if split < 100 or (n_total - split) < 50:
        return []

    is_close = close[:split]
    oos_close = close[split:]
    is_macro = {k: v[:split] for k, v in macro.items()}
    oos_macro = {k: v[split:] for k, v in macro.items()}

    is_n = len(is_close)
    oos_n = len(oos_close)
    oos_bh = bh_return(oos_close)
    oos_years = round(oos_n / 252.0, 2)

    results = []

    def _add(exp_name, params_str, is_eq, is_trades, oos_eq, oos_trades):
        is_met = compute_metrics(is_eq, is_n, is_trades)
        oos_met = compute_metrics(oos_eq, oos_n, oos_trades)
        if is_met is None or oos_met is None:
            return
        results.append({
            "target_symbol": target_sym,
            "experiment": exp_name,
            "params": params_str,
            "is_return": round(is_met["total_return"], 4),
            "is_sharpe": round(is_met["sharpe"], 4),
            "is_maxdd": round(is_met["maxdd"], 4),
            "is_trades": is_met["trades"],
            "oos_return": round(oos_met["total_return"], 4),
            "oos_sharpe": round(oos_met["sharpe"], 4),
            "oos_maxdd": round(oos_met["maxdd"], 4),
            "oos_calmar": round(oos_met["calmar"], 4),
            "oos_trades": oos_met["trades"],
            "bh_return": round(oos_bh, 4),
            "vs_bh": round(oos_met["total_return"] - oos_bh, 4),
            "years": oos_years,
            "trades_per_year": oos_met["trades_per_year"],
        })

    # Exp1: Oil filter (600 combos per target)
    for ma in OIL_MA:
        for strat in OIL_STRATEGY:
            for sens in OIL_SENSITIVITY:
                for conf in OIL_CONFIRM:
                    for rsi_buy in OIL_RSI_BUY:
                        params = f"ma={ma}|strat={strat}|sens={sens}|conf={conf}|rsi={rsi_buy}"
                        is_eq, is_tr = exp1_oil_filter(is_close, is_macro, rsi_buy, ma, strat, sens, conf)
                        oos_eq, oos_tr = exp1_oil_filter(oos_close, oos_macro, rsi_buy, ma, strat, sens, conf)
                        _add("oil_filter", params, is_eq, is_tr, oos_eq, oos_tr)

    # Exp2: Natgas spike (36 combos per target energy only)
    if target_sym in ENERGY:
        for sp in GAS_SPIKE:
            for sw in GAS_SPIKE_WINDOW:
                for act in GAS_ACTION:
                    params = f"spike={sp}|win={sw}|action={act}"
                    is_eq, is_tr = exp2_gas_spike(is_close, is_macro, sp, sw, act)
                    oos_eq, oos_tr = exp2_gas_spike(oos_close, oos_macro, sp, sw, act)
                    _add("gas_spike", params, is_eq, is_tr, oos_eq, oos_tr)

    # Exp3: Oil+Gas regime (45 combos per target energy only)
    if target_sym in ENERGY:
        for or_ in REGIME_VALS:
            for gr in REGIME_VALS:
                for st in OILGAS_STRATEGY:
                    params = f"oil={or_}|gas={gr}|strat={st}"
                    is_eq, is_tr = exp3_oil_gas_regime(is_close, is_macro, or_, gr, st)
                    oos_eq, oos_tr = exp3_oil_gas_regime(oos_close, oos_macro, or_, gr, st)
                    _add("oil_gas_regime", params, is_eq, is_tr, oos_eq, oos_tr)

    # Exp4: Dividend B&H (only dividend symbols)
    if target_sym in DIVIDEND_SYMS:
        for reinv in DIV_REINVEST:
            for tax in DIV_TAX:
                params = f"reinvest={reinv}|tax={tax}"
                is_eq, is_tr = exp4_dividend_bh(is_close, reinv, tax)
                oos_eq, oos_tr = exp4_dividend_bh(oos_close, reinv, tax)
                _add("dividend_bh", params, is_eq, is_tr, oos_eq, oos_tr)

    # Exp5: Macro regime (pruned to ~76 per target -> ~1600 total)
    for ind in MACRO_INDICATORS:
        for lb in MACRO_LOOKBACK:
            for th in MACRO_THRESHOLD:
                for act in MACRO_ACTION:
                    for conf in MACRO_CONFIRM:
                        params = f"ind={ind}|lb={lb}|th={th}|act={act}|conf={conf}"
                        is_eq, is_tr = exp5_macro_regime(is_close, is_macro, ind, lb, th, act, conf)
                        oos_eq, oos_tr = exp5_macro_regime(oos_close, oos_macro, ind, lb, th, act, conf)
                        _add("macro_regime", params, is_eq, is_tr, oos_eq, oos_tr)

    # Exp6: Regime switching (144 combos per target)
    for ri in REGIME_IND:
        for lb in REGIME_LOOKBACK:
            for sm_idx, sm in enumerate(REGIME_STRATEGY_MAP):
                for th in REGIME_THRESHOLD:
                    params = f"ind={ri}|lb={lb}|map={sm_idx}|th={th}"
                    is_eq, is_tr = exp6_regime_switch(is_close, is_macro, ri, lb, sm, th)
                    oos_eq, oos_tr = exp6_regime_switch(oos_close, oos_macro, ri, lb, sm, th)
                    _add("regime_switch", params, is_eq, is_tr, oos_eq, oos_tr)

    # Exp7: VIX spike proxy (subset: 3 spike * 3 win * 3 delay * 13 exit = 351 per target)
    vix_is = is_macro["vix"]
    vix_oos = oos_macro["vix"]
    for sp_th in VIX_SPIKE_THRESH[::2]:  # prune: every other -> 3
        for sw in SPIKE_WIN[::2]:  # prune -> 2
            is_mask = detect_spike(vix_is, sw, sp_th)
            oos_mask = detect_spike(vix_oos, sw, sp_th)
            for ed in ENTRY_DELAY[::2]:  # prune -> 3
                for em, ep in EXIT_METHODS:
                    params = f"vix_sp={sp_th}|win={sw}|delay={ed}|exit={em}_{ep}"
                    is_eq, is_tr = event_backtest(is_close, is_mask, ed, em, ep, vix=vix_is)
                    oos_eq, oos_tr = event_backtest(oos_close, oos_mask, ed, em, ep, vix=vix_oos)
                    _add("vix_spike", params, is_eq, is_tr, oos_eq, oos_tr)

    # Exp8: Oil spike proxy (energy targets only)
    if target_sym in ENERGY:
        oil_is = is_macro["oil"]
        oil_oos = oos_macro["oil"]
        for sp_th in OIL_SPIKE_THRESH[::2]:  # 3
            for sw in SPIKE_WIN[::2]:  # 2
                is_mask = detect_spike(oil_is, sw, sp_th)
                oos_mask = detect_spike(oil_oos, sw, sp_th)
                for ed in ENTRY_DELAY[::2]:  # 3
                    for em, ep in EXIT_METHODS:
                        params = f"oil_sp={sp_th}|win={sw}|delay={ed}|exit={em}_{ep}"
                        is_eq, is_tr = event_backtest(is_close, is_mask, ed, em, ep, vix=vix_is)
                        oos_eq, oos_tr = event_backtest(oos_close, oos_mask, ed, em, ep, vix=vix_oos)
                        _add("oil_spike", params, is_eq, is_tr, oos_eq, oos_tr)

    # Exp9: Gold spike proxy
    gold_is = is_macro["gold"]
    gold_oos = oos_macro["gold"]
    for sp_th in GOLD_SPIKE_THRESH[::2]:  # 3
        for sw in SPIKE_WIN[::2]:  # 2
            is_mask = detect_spike(gold_is, sw, sp_th)
            oos_mask = detect_spike(gold_oos, sw, sp_th)
            for ed in ENTRY_DELAY[::2]:  # 3
                for em, ep in EXIT_METHODS:
                    params = f"gold_sp={sp_th}|win={sw}|delay={ed}|exit={em}_{ep}"
                    is_eq, is_tr = event_backtest(is_close, is_mask, ed, em, ep, vix=vix_is)
                    oos_eq, oos_tr = event_backtest(oos_close, oos_mask, ed, em, ep, vix=vix_oos)
                    _add("gold_spike", params, is_eq, is_tr, oos_eq, oos_tr)

    # Exp10: Defense spike proxy (use G_DEFENSE_AVG)
    if G_DEFENSE_AVG is not None and target_sym in ENERGY:
        def_is = G_DEFENSE_AVG[:split]
        def_oos = G_DEFENSE_AVG[split:]
        for sp_th in DEFENSE_SPIKE_THRESH[::2]:  # 2
            for sw in SPIKE_WIN[::2]:  # 2
                is_mask = detect_spike(def_is, sw, sp_th)
                oos_mask = detect_spike(def_oos, sw, sp_th)
                for ed in ENTRY_DELAY[::2]:  # 3
                    for em, ep in EXIT_METHODS:
                        params = f"def_sp={sp_th}|win={sw}|delay={ed}|exit={em}_{ep}"
                        is_eq, is_tr = event_backtest(is_close, is_mask, ed, em, ep, vix=vix_is)
                        oos_eq, oos_tr = event_backtest(oos_close, oos_mask, ed, em, ep, vix=vix_oos)
                        _add("defense_spike", params, is_eq, is_tr, oos_eq, oos_tr)

    # Exp11: Composite signal (2+ spikes simultaneously)
    for min_count in COMPOSITE_MIN:
        for sw in SPIKE_WIN[::2]:  # 2
            # Build composite mask from VIX, oil, gold spikes
            is_vix_m = detect_spike(vix_is, sw, 0.20)
            oos_vix_m = detect_spike(vix_oos, sw, 0.20)
            is_oil_m = detect_spike(is_macro["oil"], sw, 0.10)
            oos_oil_m = detect_spike(oos_macro["oil"], sw, 0.10)
            is_gold_m = detect_spike(is_macro["gold"], sw, 0.05)
            oos_gold_m = detect_spike(oos_macro["gold"], sw, 0.05)
            is_cop_m = detect_spike(is_macro["copper"], sw, 0.10)
            oos_cop_m = detect_spike(oos_macro["copper"], sw, 0.10)

            is_count = (is_vix_m.astype(int) + is_oil_m.astype(int) +
                        is_gold_m.astype(int) + is_cop_m.astype(int))
            oos_count = (oos_vix_m.astype(int) + oos_oil_m.astype(int) +
                         oos_gold_m.astype(int) + oos_cop_m.astype(int))

            is_mask = is_count >= min_count
            oos_mask = oos_count >= min_count

            for ed in ENTRY_DELAY[::2]:  # 3
                for em, ep in EXIT_METHODS[:8]:  # prune exits
                    params = f"min={min_count}|win={sw}|delay={ed}|exit={em}_{ep}"
                    is_eq, is_tr = event_backtest(is_close, is_mask, ed, em, ep, vix=vix_is)
                    oos_eq, oos_tr = event_backtest(oos_close, oos_mask, ed, em, ep, vix=vix_oos)
                    _add("composite_spike", params, is_eq, is_tr, oos_eq, oos_tr)

    # Exp12: Beta filter (20 combos per target)
    if G_SPY_CLOSE is not None:
        spy_is = G_SPY_CLOSE[:split]
        spy_oos = G_SPY_CLOSE[split:]
        for bw in BETA_WIN:
            for bt in BETA_THRESH:
                params = f"win={bw}|thresh={bt}"
                is_eq, is_tr = exp12_beta_filter(is_close, spy_is, bw, bt)
                oos_eq, oos_tr = exp12_beta_filter(oos_close, spy_oos, bw, bt)
                _add("beta_filter", params, is_eq, is_tr, oos_eq, oos_tr)

    return results


def _worker(target_sym):
    """Multiprocessing worker."""
    try:
        return process_target(target_sym)
    except Exception as e:
        print(f"  ERROR {target_sym}: {e}")
        return []


def main():
    global G_DATA, G_DEFENSE_AVG, G_SPY_CLOSE

    t0 = time.time()

    # -- Load data --
    print("Loading data...")
    all_close = {}
    macro_close = {}

    # Load target symbols
    for sym in ALL_TARGETS:
        path = DATA_DIR / f"{sym}.parquet"
        if not path.exists():
            print(f"  {sym}: MISSING")
            continue
        df = pd.read_parquet(path)
        s = df["close"].copy()
        s.index = pd.to_datetime(s.index)
        all_close[sym] = s
        print(f"  {sym}: {len(s)} days")

    # Load macro symbols
    for sym, alias in MACRO_SYMS.items():
        path = DATA_DIR / f"{sym}.parquet"
        if not path.exists():
            print(f"  {sym} ({alias}): MISSING")
            continue
        df = pd.read_parquet(path)
        s = df["close"].copy()
        s.index = pd.to_datetime(s.index)
        macro_close[alias] = s
        print(f"  {sym} ({alias}): {len(s)} days")

    # Load SPY for beta
    spy_path = DATA_DIR / "SPY.parquet"
    spy_series = None
    if spy_path.exists():
        df = pd.read_parquet(spy_path)
        spy_series = df["close"].copy()
        spy_series.index = pd.to_datetime(spy_series.index)
        print(f"  SPY: {len(spy_series)} days")

    print(f"Loaded {len(all_close)} targets, {len(macro_close)} macro\n")

    # -- Align data --
    print("Aligning data...")

    # Find common dates across all macro indicators
    macro_keys = list(macro_close.keys())
    if not macro_keys:
        print("ERROR: No macro data loaded.")
        return

    common_macro_idx = macro_close[macro_keys[0]].index
    for k in macro_keys[1:]:
        common_macro_idx = common_macro_idx.intersection(macro_close[k].index)

    if spy_series is not None:
        common_macro_idx = common_macro_idx.intersection(spy_series.index)

    common_macro_idx = common_macro_idx.sort_values()
    print(f"  Common macro dates: {len(common_macro_idx)}")

    # Build aligned macro arrays
    macro_aligned = {}
    for k in macro_keys:
        macro_aligned[k] = macro_close[k].reindex(common_macro_idx).ffill().values.astype(np.float64)

    spy_aligned = None
    if spy_series is not None:
        spy_aligned = spy_series.reindex(common_macro_idx).ffill().values.astype(np.float64)

    # Defense average (for composite)
    defense_closes = []
    for sym in DEFENSE:
        if sym in all_close:
            s = all_close[sym].reindex(common_macro_idx).ffill()
            defense_closes.append(s.values)
    defense_avg = None
    if defense_closes:
        # Normalize each to start at 100, then average
        normed = []
        for dc in defense_closes:
            valid = dc[~np.isnan(dc)]
            if len(valid) > 0:
                normed.append(dc / valid[0] * 100.0)
        if normed:
            defense_avg = np.nanmean(np.column_stack(normed), axis=1)

    # Build per-target aligned data
    valid_targets = []
    for sym in ALL_TARGETS:
        if sym not in all_close:
            continue
        sym_idx = common_macro_idx.intersection(all_close[sym].index)
        if len(sym_idx) < 500:
            print(f"  {sym}: only {len(sym_idx)} overlap days, skipping")
            continue

        sym_idx = sym_idx.sort_values()
        # Map back to common_macro_idx positions for macro alignment
        pos = common_macro_idx.get_indexer(sym_idx)
        valid_pos = pos[pos >= 0]
        if len(valid_pos) < 500:
            print(f"  {sym}: only {len(valid_pos)} valid pos, skipping")
            continue

        target_close = all_close[sym].reindex(common_macro_idx).ffill().values.astype(np.float64)
        # Use full common_macro_idx for alignment
        G_DATA[sym] = {
            "close": target_close,
            "macro": macro_aligned,
        }
        valid_targets.append(sym)

    G_DEFENSE_AVG = defense_avg
    G_SPY_CLOSE = spy_aligned

    print(f"  Valid targets: {len(valid_targets)} / {len(ALL_TARGETS)}")
    print(f"  Data alignment done ({time.time()-t0:.1f}s)\n")

    if not valid_targets:
        print("ERROR: No valid targets.")
        return

    # -- Process --
    n_workers = max(1, mp.cpu_count() - 1)
    print(f"Processing {len(valid_targets)} targets with {n_workers} workers (fork)...")
    sys.stdout.flush()

    all_results = []
    ctx = mp.get_context("fork")
    with ctx.Pool(n_workers) as pool:
        for i, target_results in enumerate(pool.imap_unordered(_worker, valid_targets)):
            all_results.extend(target_results)
            elapsed = time.time() - t0
            print(f"  [{i+1}/{len(valid_targets)}] done | "
                  f"results so far: {len(all_results):,} | {elapsed:.1f}s")
            sys.stdout.flush()

    elapsed = time.time() - t0
    print(f"\nDone! {len(all_results):,} valid results in {elapsed:.1f}s\n")

    # -- Save --
    df = pd.DataFrame(all_results)
    csv_path = RESULTS_DIR / "energy_macro_results.csv"
    df.to_csv(csv_path, index=False)
    print(f"Saved to {csv_path}\n")

    if df.empty:
        print("No valid results.")
        return

    # -- Summaries --
    cols = ["target_symbol", "experiment", "params",
            "oos_return", "oos_sharpe", "oos_maxdd", "oos_calmar",
            "oos_trades", "bh_return", "vs_bh", "years", "trades_per_year"]

    print("=" * 140)
    print("TOP 20 BY OOS SHARPE (ALL EXPERIMENTS)")
    print("=" * 140)
    print(df.nlargest(20, "oos_sharpe")[cols].to_string(index=False))
    print()

    print("=" * 140)
    print("TOP 20 BY OOS CALMAR (ALL EXPERIMENTS)")
    print("=" * 140)
    print(df.nlargest(20, "oos_calmar")[cols].to_string(index=False))
    print()

    # Per-experiment summary
    print("=" * 140)
    print("PER-EXPERIMENT STATISTICS")
    print("=" * 140)
    for exp_name in sorted(df["experiment"].unique()):
        sub = df[df["experiment"] == exp_name]
        if sub.empty:
            continue
        pos_bh = (sub["vs_bh"] > 0).sum()
        print(f"\n{exp_name} ({len(sub):,} combos):")
        print(f"  OOS Sharpe: mean={sub['oos_sharpe'].mean():.3f}, "
              f"median={sub['oos_sharpe'].median():.3f}, max={sub['oos_sharpe'].max():.3f}")
        print(f"  OOS Return: mean={sub['oos_return'].mean():.3f}, "
              f"median={sub['oos_return'].median():.3f}, max={sub['oos_return'].max():.3f}")
        print(f"  OOS MaxDD:  mean={sub['oos_maxdd'].mean():.3f}, "
              f"worst={sub['oos_maxdd'].min():.3f}")
        print(f"  vs B&H positive: {pos_bh}/{len(sub)} ({pos_bh/len(sub)*100:.1f}%)")
        print(f"  Avg trades/yr: {sub['trades_per_year'].mean():.1f}")
    print()

    # Top by experiment
    for exp_name in sorted(df["experiment"].unique()):
        sub = df[df["experiment"] == exp_name]
        if sub.empty:
            continue
        print("=" * 140)
        print(f"TOP 10 BY OOS SHARPE - {exp_name.upper()}")
        print("=" * 140)
        print(sub.nlargest(10, "oos_sharpe")[cols].to_string(index=False))
        print()

    # SHV baseline comparison
    print("=" * 140)
    print("SHV BASELINE: CAGR 1.52%, MDD -0.45% (2007-2026, 19yr)")
    print("=" * 140)
    shv_cagr = 0.0152
    above_shv = df[df["oos_sharpe"] > 0.5]  # rough filter for strategies beating risk-free
    print(f"Strategies with OOS Sharpe > 0.5: {len(above_shv):,} / {len(df):,} "
          f"({len(above_shv)/len(df)*100:.1f}%)")
    print()


if __name__ == "__main__":
    main()
