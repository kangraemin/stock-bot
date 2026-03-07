"""Experiment: Energy Sector 9-Strategy Backtest (~4.85M combinations)

15 energy symbols x 9 strategies with full parameter grids.
- IS/OOS split: first 70% / last 30%
- Self-contained (no imports from backtest/)
- numpy-based simulation
- Pool(cpu_count()-1), imap_unordered
- Results saved to results/energy_strategies_results.csv
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
FEE_RATE = 0.0025  # 0.25%
MIN_DAYS = 252

ENERGY = [
    "CVX", "XOM", "XLE", "XOP", "OIH", "FANG", "VDE", "ERX",
    "COP", "SLB", "EOG", "MPC", "PSX", "HAL", "DVN",
]

# ══════════════════════════════════════════════════════════════════════
# Parameter Grids
# ══════════════════════════════════════════════════════════════════════

# 1. BB+RSI+EMA
BB_WIN = [10, 15, 20, 25, 30]
BB_STD = [1.5, 2.0, 2.5, 3.0]
RSI_WIN_BB = [7, 14, 21]
RSI_BUY_BB = [20, 25, 30, 35, 40, 45]
RSI_SELL_BB = [55, 60, 65, 70, 75, 80]
EMA_WIN = [20, 50, 100, 200]
EMA_FILTER = [True, False]

# 2. RSI standalone
RSI_WIN_SOLO = [5, 7, 9, 14, 21, 30, 50]
OVERSOLD = [15, 20, 25, 30, 35, 40]
OVERBOUGHT = [55, 60, 65, 70, 75, 80, 85]
RSI_EXIT = ["rsi_cross", "hold_20d", "hold_60d", "trail_15pct"]

# 3. DCA
DCA_FREQ = [1, 5, 10, 21]
DCA_RSI_SCHEME = ["none", "linear", "threshold", "tiered", "inverse_sigmoid", "vol_scaled"]
DCA_RSI_PERIOD = [14, 30]
DCA_BOOST = [1.5, 2.0]

# 4. Trailing stop
TRAIL_PCT = [0.03, 0.05, 0.07, 0.10, 0.15, 0.20]
ATR_MULT = [1.0, 1.5, 2.0, 2.5, 3.0]
ATR_WIN = [7, 14, 21]
USE_ATR = [True, False]

# 5. Momentum
MOM_LOOKBACK = [5, 10, 21, 42, 63, 126]
MOM_THRESHOLD = [0.01, 0.02, 0.03, 0.05, 0.07, 0.10]
MOM_HOLD = [5, 10, 21, 42, 63, 126]

# 6. MACD
MACD_FAST = [8, 12, 16, 20]
MACD_SLOW = [21, 26, 30, 40]
MACD_SIGNAL = [5, 9, 12, 15]
MACD_FILTER = ["none", "rsi_above_50", "above_sma200", "vol_expand"]

# 7. Multi-timeframe
MTF_WEEKLY_RSI_BUY = [30, 35, 40, 45]
MTF_DAILY_STRATEGY = ["bb_rsi", "rsi_only", "macd", "momentum"]
MTF_WEEKLY_BB_FILTER = [True, False]

# 8. Seasonality
AVOID_MONTHS_LIST = [
    [9], [8, 9], [6, 7, 8], [1], [5, 6, 7, 8, 9, 10],
    [2, 3], [7, 8, 9], [4, 5], [6, 7], [8, 9, 10],
    [1, 2], [3, 4, 5], [11, 12], [5, 6], [9, 10],
    [6, 7, 8, 9], [1, 6, 7, 8, 9], [5, 6, 7, 8, 9],
    [7, 8], [2, 3, 4],
]
BUY_MONTHS_LIST = [
    [10, 11, 12], [11], [1, 2, 3, 4], [10, 11], [3, 4],
    [11, 12, 1], [1, 2, 3], [9, 10, 11, 12], [4, 5, 6],
    [10, 11, 12, 1, 2], [11, 12, 1, 2], [6, 7, 8, 9],
    [1, 2, 3, 4, 5], [3, 4, 5, 6], [10, 11, 12, 1],
    [2, 3, 4, 5], [10, 11, 12, 1, 2, 3], [11, 12, 1, 2, 3],
    [4, 5, 6, 7], [7, 8, 9, 10],
]
SEASON_HOLD_DAYS = [21, 42, 63, 126]

# 9. Volatility targeting
TARGET_VOL = [0.10, 0.15, 0.20, 0.25, 0.30]
VOL_WIN = [10, 21, 42, 63]
LEV_CAP = [1.0, 1.5, 2.0, 3.0]
VOL_REBAL = ["daily", "weekly"]


# ══════════════════════════════════════════════════════════════════════
# Indicator Functions (numpy)
# ══════════════════════════════════════════════════════════════════════

def compute_rsi(close, period):
    """Wilder's RSI using EMA."""
    delta = np.diff(close, prepend=close[0])
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)

    alpha = 1.0 / period
    n = len(close)
    avg_gain = np.zeros(n)
    avg_loss = np.zeros(n)

    if n < period + 1:
        return np.full(n, 50.0)

    avg_gain[period] = np.mean(gain[1: period + 1])
    avg_loss[period] = np.mean(loss[1: period + 1])

    for i in range(period + 1, n):
        avg_gain[i] = avg_gain[i - 1] * (1 - alpha) + gain[i] * alpha
        avg_loss[i] = avg_loss[i - 1] * (1 - alpha) + loss[i] * alpha

    rs = np.divide(avg_gain, avg_loss, out=np.ones(n), where=avg_loss != 0)
    rsi = 100.0 - 100.0 / (1.0 + rs)
    rsi[:period] = 50.0
    return rsi


def compute_bb(close, window, num_std):
    """Bollinger Bands: returns (upper, lower)."""
    n = len(close)
    upper = np.full(n, np.nan)
    lower = np.full(n, np.nan)
    for i in range(window - 1, n):
        seg = close[i - window + 1: i + 1]
        m = np.mean(seg)
        s = np.std(seg)
        upper[i] = m + num_std * s
        lower[i] = m - num_std * s
    return upper, lower


def compute_ema(close, window):
    """Exponential Moving Average."""
    n = len(close)
    ema = np.zeros(n)
    ema[0] = close[0]
    alpha = 2.0 / (window + 1)
    for i in range(1, n):
        ema[i] = alpha * close[i] + (1 - alpha) * ema[i - 1]
    return ema


def compute_sma(close, window):
    """Simple Moving Average."""
    n = len(close)
    sma = np.full(n, np.nan)
    for i in range(window - 1, n):
        sma[i] = np.mean(close[i - window + 1: i + 1])
    return sma


def compute_atr(high, low, close, window):
    """Average True Range."""
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
    """MACD line, signal line, histogram."""
    ema_fast = compute_ema(close, fast)
    ema_slow = compute_ema(close, slow)
    macd_line = ema_fast - ema_slow
    signal_line = compute_ema(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


# ══════════════════════════════════════════════════════════════════════
# Simulation & Metrics
# ══════════════════════════════════════════════════════════════════════

def simulate_long_only(close, buy_signals, sell_signals, capital=2000.0, fee=0.0025):
    """Simple long-only simulation. Returns (equity_curve, total_trades)."""
    n = len(close)
    equity = np.full(n, capital, dtype=np.float64)
    position = 0.0
    cash = capital
    trades = 0

    for i in range(1, n):
        if buy_signals[i] and position == 0:
            shares = cash * (1 - fee) / close[i]
            position = shares
            cash = 0.0
            trades += 1
        elif sell_signals[i] and position > 0:
            cash = position * close[i] * (1 - fee)
            position = 0.0
            trades += 1
        equity[i] = cash + position * close[i]

    return equity, trades


def simulate_trailing_stop(close, high, low, buy_signals, trail_pct=None,
                           atr_vals=None, atr_mult=1.0, use_atr=False,
                           capital=2000.0, fee=0.0025):
    """Long-only with trailing stop exit."""
    n = len(close)
    equity = np.full(n, capital, dtype=np.float64)
    position = 0.0
    cash = capital
    trades = 0
    entry_price = 0.0
    highest_since_entry = 0.0

    for i in range(1, n):
        if position > 0:
            if high[i] > highest_since_entry:
                highest_since_entry = high[i]
            if use_atr and atr_vals is not None and atr_vals[i] > 0:
                stop_level = highest_since_entry - atr_mult * atr_vals[i]
            else:
                stop_level = highest_since_entry * (1 - trail_pct)
            if low[i] <= stop_level:
                sell_price = max(stop_level, low[i])
                cash = position * sell_price * (1 - fee)
                position = 0.0
                trades += 1

        if buy_signals[i] and position == 0:
            shares = cash * (1 - fee) / close[i]
            position = shares
            cash = 0.0
            trades += 1
            entry_price = close[i]
            highest_since_entry = high[i]

        equity[i] = cash + position * close[i]

    return equity, trades


def simulate_dca(close, rsi, frequency, scheme, boost_mult,
                 initial_capital=2000.0, dca_amount=100.0, fee=0.0025):
    """DCA simulation with RSI-weighted amounts."""
    n = len(close)
    shares = initial_capital / (close[0] * (1 + fee))
    total_invested = initial_capital
    n_trades = 1
    equity = np.zeros(n)

    for i in range(n):
        if i > 0 and i % frequency == 0:
            w = _dca_weight(rsi[i], scheme, boost_mult)
            amount = dca_amount * w
            if amount > 0:
                shares += amount / (close[i] * (1 + fee))
                total_invested += amount
                n_trades += 1
        equity[i] = shares * close[i]

    return equity, n_trades, total_invested


def _dca_weight(rsi_val, scheme, boost_mult):
    """Weight multiplier for DCA based on RSI scheme."""
    if scheme == "none":
        return 1.0
    elif scheme == "linear":
        return max((100.0 - rsi_val) / 50.0, 0.0)
    elif scheme == "threshold":
        return boost_mult if rsi_val < 50.0 else 0.0
    elif scheme == "tiered":
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
    elif scheme == "inverse_sigmoid":
        x = (rsi_val - 50.0) / 15.0
        return max(2.0 / (1.0 + np.exp(x)), 0.0)
    elif scheme == "vol_scaled":
        # Simple: low RSI = high weight, but capped at boost_mult
        if rsi_val < 30:
            return boost_mult
        elif rsi_val < 50:
            return 1.0 + (boost_mult - 1.0) * (50.0 - rsi_val) / 20.0
        else:
            return 1.0
    return 1.0


def simulate_vol_target(close, target_vol, vol_win, lev_cap, rebal,
                        capital=2000.0, fee=0.0025):
    """Volatility targeting: scale exposure to target annualized vol."""
    n = len(close)
    equity = np.full(n, capital, dtype=np.float64)
    cash = capital
    position = 0.0
    rebal_freq = 1 if rebal == "daily" else 5

    log_ret = np.zeros(n)
    for i in range(1, n):
        log_ret[i] = np.log(close[i] / close[i - 1])

    for i in range(1, n):
        # Rebalance check
        if i >= vol_win and i % rebal_freq == 0:
            realized_vol = np.std(log_ret[max(1, i - vol_win): i]) * np.sqrt(252)
            if realized_vol > 1e-8:
                target_lev = min(target_vol / realized_vol, lev_cap)
            else:
                target_lev = lev_cap

            current_value = cash + position * close[i]
            target_position_value = current_value * target_lev
            target_shares = target_position_value / close[i]
            delta_shares = target_shares - position

            if abs(delta_shares) > 0.001:
                if delta_shares > 0:
                    cost = delta_shares * close[i] * (1 + fee)
                    if cost <= cash:
                        position += delta_shares
                        cash -= cost
                else:
                    proceeds = abs(delta_shares) * close[i] * (1 - fee)
                    position += delta_shares  # negative
                    cash += proceeds

        equity[i] = cash + position * close[i]

    trades = n // rebal_freq  # approximate
    return equity, trades


def compute_metrics(equity, total_trades, periods_per_year=252):
    """Compute key performance metrics from equity curve."""
    if len(equity) < 2 or equity[0] <= 0:
        return {
            'total_return': 0, 'ann_return': 0, 'sharpe': 0,
            'maxdd': 0, 'calmar': 0, 'trades': 0,
            'trades_per_year': 0, 'years': 0,
        }

    returns = np.diff(equity) / np.where(equity[:-1] != 0, equity[:-1], 1.0)
    returns = returns[np.isfinite(returns)]
    total_return = equity[-1] / equity[0] - 1
    n_years = len(equity) / periods_per_year

    if n_years > 0 and total_return > -1:
        ann_return = (1 + total_return) ** (1 / n_years) - 1
    else:
        ann_return = 0.0

    if len(returns) > 1 and np.std(returns) > 0:
        sharpe = np.mean(returns) / np.std(returns) * np.sqrt(252)
    else:
        sharpe = 0.0

    peak = np.maximum.accumulate(equity)
    dd = (equity - peak) / np.where(peak != 0, peak, 1.0)
    maxdd = np.min(dd)

    calmar = ann_return / abs(maxdd) if maxdd != 0 else 0.0
    trades_per_year = total_trades / n_years if n_years > 0 else 0.0

    return {
        'total_return': total_return,
        'ann_return': ann_return,
        'sharpe': sharpe,
        'maxdd': maxdd,
        'calmar': calmar,
        'trades': total_trades,
        'trades_per_year': trades_per_year,
        'years': round(n_years, 2),
    }


# ══════════════════════════════════════════════════════════════════════
# Strategy Runners
# ══════════════════════════════════════════════════════════════════════

def run_bb_rsi_ema(close, indicators, is_end):
    """Strategy 1: BB + RSI + EMA mean reversion."""
    results = []
    for bb_win, bb_std, rsi_win, rsi_buy, rsi_sell, ema_win, ema_filt in product(
        BB_WIN, BB_STD, RSI_WIN_BB, RSI_BUY_BB, RSI_SELL_BB, EMA_WIN, EMA_FILTER
    ):
        rsi = indicators['rsi'].get(rsi_win)
        if rsi is None:
            continue
        bb_key = (bb_win, bb_std)
        if bb_key not in indicators['bb']:
            continue
        bb_upper, bb_lower = indicators['bb'][bb_key]
        ema = indicators['ema'].get(ema_win)
        if ema is None:
            continue

        n = len(close)
        buy_sig = np.zeros(n, dtype=bool)
        sell_sig = np.zeros(n, dtype=bool)

        for i in range(max(bb_win, ema_win), n):
            if np.isnan(bb_lower[i]):
                continue
            buy_cond = (close[i] < bb_lower[i]) and (rsi[i] < rsi_buy)
            if ema_filt:
                buy_cond = buy_cond and (close[i] > ema[i])
            sell_cond = (close[i] > bb_upper[i]) and (rsi[i] > rsi_sell)
            buy_sig[i] = buy_cond
            sell_sig[i] = sell_cond

        params = f"bb={bb_win}/{bb_std},rsi={rsi_win}/{rsi_buy}/{rsi_sell},ema={ema_win},filt={ema_filt}"
        results.append(_eval_strategy(close, buy_sig, sell_sig, is_end, "bb_rsi_ema", params))

    return results


def run_rsi_solo(close, indicators, is_end):
    """Strategy 2: RSI standalone."""
    results = []
    for rsi_win, oversold, overbought, exit_mode in product(
        RSI_WIN_SOLO, OVERSOLD, OVERBOUGHT, RSI_EXIT
    ):
        if oversold >= overbought:
            continue

        rsi = indicators['rsi'].get(rsi_win)
        if rsi is None:
            continue

        n = len(close)
        buy_sig = np.zeros(n, dtype=bool)
        sell_sig = np.zeros(n, dtype=bool)

        holding = False
        entry_bar = 0
        entry_price = 0.0
        peak_price = 0.0

        for i in range(rsi_win, n):
            if not holding:
                if rsi[i] < oversold:
                    buy_sig[i] = True
                    holding = True
                    entry_bar = i
                    entry_price = close[i]
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

        params = f"rsi={rsi_win}/{oversold}/{overbought},exit={exit_mode}"
        results.append(_eval_strategy(close, buy_sig, sell_sig, is_end, "rsi_solo", params))

    return results


def run_dca(close, indicators, is_end):
    """Strategy 3: DCA with RSI weighting."""
    results = []
    for freq, scheme, rsi_period, boost in product(
        DCA_FREQ, DCA_RSI_SCHEME, DCA_RSI_PERIOD, DCA_BOOST
    ):
        rsi = indicators['rsi'].get(rsi_period)
        if rsi is None:
            continue

        close_is = close[:is_end]
        close_oos = close[is_end:]
        rsi_is = rsi[:is_end]
        rsi_oos = rsi[is_end:]

        if len(close_is) < MIN_DAYS or len(close_oos) < 60:
            continue

        eq_is, tr_is, inv_is = simulate_dca(close_is, rsi_is, freq, scheme, boost)
        eq_oos, tr_oos, inv_oos = simulate_dca(close_oos, rsi_oos, freq, scheme, boost)

        m_is = _compute_dca_metrics(eq_is, inv_is, tr_is)
        m_oos = _compute_dca_metrics(eq_oos, inv_oos, tr_oos)

        bh_return = close_oos[-1] / close_oos[0] - 1
        total_years = len(close) / 252.0
        oos_years = len(close_oos) / 252.0

        params = f"freq={freq},scheme={scheme},rsi_p={rsi_period},boost={boost}"
        results.append({
            'strategy': 'dca',
            'params': params,
            'is_return': round(m_is['total_return'], 6),
            'is_sharpe': round(m_is['sharpe'], 4),
            'is_maxdd': round(m_is['maxdd'], 4),
            'is_trades': m_is['trades'],
            'oos_return': round(m_oos['total_return'], 6),
            'oos_sharpe': round(m_oos['sharpe'], 4),
            'oos_maxdd': round(m_oos['maxdd'], 4),
            'oos_calmar': round(m_oos['calmar'], 4),
            'oos_trades': m_oos['trades'],
            'bh_return': round(bh_return, 6),
            'vs_bh': round(m_oos['total_return'] - bh_return, 6),
            'years': round(total_years, 2),
            'trades_per_year': round((tr_is + tr_oos) / total_years, 2) if total_years > 0 else 0,
        })

    return results


def _compute_dca_metrics(equity, total_invested, n_trades):
    """Metrics for DCA (return based on invested amount)."""
    if len(equity) < 2 or total_invested <= 0:
        return {'total_return': 0, 'sharpe': 0, 'maxdd': 0, 'calmar': 0, 'trades': 0}

    total_return = (equity[-1] - total_invested) / total_invested
    n_years = len(equity) / 252.0
    ann_return = (1 + total_return) ** (1 / n_years) - 1 if n_years > 0 and total_return > -1 else 0

    returns = np.diff(equity) / np.where(equity[:-1] != 0, equity[:-1], 1.0)
    returns = returns[np.isfinite(returns)]
    sharpe = np.mean(returns) / (np.std(returns) + 1e-10) * np.sqrt(252) if len(returns) > 1 else 0

    peak = np.maximum.accumulate(equity)
    dd = (equity - peak) / np.where(peak != 0, peak, 1.0)
    maxdd = np.min(dd)
    calmar = ann_return / abs(maxdd) if maxdd != 0 else 0

    return {'total_return': total_return, 'sharpe': sharpe, 'maxdd': maxdd,
            'calmar': calmar, 'trades': n_trades}


def run_trailing_stop(close, high, low, indicators, is_end):
    """Strategy 4: BB+RSI buy + trailing stop sell."""
    results = []
    rsi14 = indicators['rsi'].get(14)
    if rsi14 is None:
        return results
    bb_upper, bb_lower = indicators['bb'].get((20, 2.0), (None, None))
    if bb_lower is None:
        return results

    n = len(close)
    buy_sig = np.zeros(n, dtype=bool)
    for i in range(20, n):
        if not np.isnan(bb_lower[i]) and close[i] < bb_lower[i] and rsi14[i] < 30:
            buy_sig[i] = True

    for use_atr in USE_ATR:
        if use_atr:
            for atr_win in ATR_WIN:
                atr_vals = indicators['atr'].get(atr_win)
                if atr_vals is None:
                    continue
                for atr_m in ATR_MULT:
                    eq, trades = simulate_trailing_stop(
                        close, high, low, buy_sig,
                        atr_vals=atr_vals, atr_mult=atr_m, use_atr=True,
                    )
                    params = f"atr_win={atr_win},atr_m={atr_m}"
                    results.append(_eval_strategy_from_eq(
                        close, eq, trades, is_end, "trailing_stop", params))
        else:
            for tpct in TRAIL_PCT:
                eq, trades = simulate_trailing_stop(
                    close, high, low, buy_sig, trail_pct=tpct, use_atr=False,
                )
                params = f"trail_pct={tpct}"
                results.append(_eval_strategy_from_eq(
                    close, eq, trades, is_end, "trailing_stop", params))

    return results


def run_momentum(close, indicators, is_end):
    """Strategy 5: Momentum (lookback return > threshold, hold N days)."""
    results = []
    for lookback, threshold, hold in product(MOM_LOOKBACK, MOM_THRESHOLD, MOM_HOLD):
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

        params = f"look={lookback},thr={threshold},hold={hold}"
        results.append(_eval_strategy(close, buy_sig, sell_sig, is_end, "momentum", params))

    return results


def run_macd(close, indicators, is_end):
    """Strategy 6: MACD histogram crossover with optional filter."""
    results = []
    rsi14 = indicators['rsi'].get(14)
    sma200 = indicators['sma'].get(200)

    for fast, slow, signal, filt in product(MACD_FAST, MACD_SLOW, MACD_SIGNAL, MACD_FILTER):
        if fast >= slow:
            continue

        macd_key = (fast, slow, signal)
        if macd_key not in indicators['macd']:
            continue
        _, _, histogram = indicators['macd'][macd_key]

        n = len(close)
        buy_sig = np.zeros(n, dtype=bool)
        sell_sig = np.zeros(n, dtype=bool)

        # Compute rolling 20-day volume std ratio for vol_expand
        vol_expand_arr = None
        if filt == "vol_expand":
            vol_expand_arr = np.zeros(n, dtype=bool)
            for i in range(20, n):
                recent_vol = np.std(np.diff(close[i - 20: i + 1]))
                long_vol = np.std(np.diff(close[max(0, i - 60): i + 1])) if i >= 60 else recent_vol
                vol_expand_arr[i] = recent_vol > long_vol * 1.2 if long_vol > 0 else False

        warmup = slow + signal
        for i in range(warmup, n):
            # Buy: histogram crosses from negative to positive
            if histogram[i] > 0 and histogram[i - 1] <= 0:
                pass_filter = True
                if filt == "rsi_above_50" and rsi14 is not None:
                    pass_filter = rsi14[i] > 50
                elif filt == "above_sma200" and sma200 is not None:
                    pass_filter = not np.isnan(sma200[i]) and close[i] > sma200[i]
                elif filt == "vol_expand" and vol_expand_arr is not None:
                    pass_filter = vol_expand_arr[i]

                if pass_filter:
                    buy_sig[i] = True

            # Sell: histogram crosses from positive to negative
            elif histogram[i] < 0 and histogram[i - 1] >= 0:
                sell_sig[i] = True

        params = f"fast={fast},slow={slow},sig={signal},filt={filt}"
        results.append(_eval_strategy(close, buy_sig, sell_sig, is_end, "macd", params))

    return results


def run_multi_timeframe(close, indicators, is_end):
    """Strategy 7: Weekly (5-day rolling) filter + daily strategy."""
    results = []
    # Weekly RSI: 5-day rolling RSI
    weekly_rsi = {}
    for period in [5, 7, 10, 14]:
        weekly_rsi[period] = compute_rsi(close, period * 5)

    rsi14 = indicators['rsi'].get(14)
    bb_upper20, bb_lower20 = indicators['bb'].get((20, 2.0), (None, None))

    for w_rsi_buy, daily_strat, w_bb_filt in product(
        MTF_WEEKLY_RSI_BUY, MTF_DAILY_STRATEGY, MTF_WEEKLY_BB_FILTER
    ):
        n = len(close)
        buy_sig = np.zeros(n, dtype=bool)
        sell_sig = np.zeros(n, dtype=bool)

        # Use period 14 weekly RSI (70 daily bars)
        w_rsi = weekly_rsi.get(14)
        if w_rsi is None:
            continue

        for i in range(200, n):
            # Weekly filter: weekly RSI < buy threshold
            weekly_ok = w_rsi[i] < w_rsi_buy
            if w_bb_filt and bb_lower20 is not None and not np.isnan(bb_lower20[i]):
                weekly_ok = weekly_ok and (close[i] < bb_lower20[i] * 1.05)

            if not weekly_ok:
                continue

            # Daily signal
            if daily_strat == "bb_rsi":
                if bb_lower20 is not None and rsi14 is not None:
                    if not np.isnan(bb_lower20[i]) and close[i] < bb_lower20[i] and rsi14[i] < 30:
                        buy_sig[i] = True
            elif daily_strat == "rsi_only":
                if rsi14 is not None and rsi14[i] < 30:
                    buy_sig[i] = True
            elif daily_strat == "macd":
                macd_key = (12, 26, 9)
                if macd_key in indicators['macd']:
                    _, _, hist = indicators['macd'][macd_key]
                    if i > 0 and hist[i] > 0 and hist[i - 1] <= 0:
                        buy_sig[i] = True
            elif daily_strat == "momentum":
                if i >= 21:
                    ret = close[i] / close[i - 21] - 1
                    if ret > 0.03:
                        buy_sig[i] = True

        # Sell: weekly RSI > 70 or RSI14 > 70
        for i in range(200, n):
            if w_rsi[i] > 70 or (rsi14 is not None and rsi14[i] > 70):
                sell_sig[i] = True

        params = f"w_rsi_buy={w_rsi_buy},daily={daily_strat},w_bb={w_bb_filt}"
        results.append(_eval_strategy(close, buy_sig, sell_sig, is_end, "multi_tf", params))

    return results


def run_seasonality(close, dates, is_end):
    """Strategy 8: Seasonal buy/avoid months."""
    results = []
    seen = set()

    for avoid, buy_months, hold_days in product(
        AVOID_MONTHS_LIST, BUY_MONTHS_LIST, SEASON_HOLD_DAYS
    ):
        # Skip if avoid and buy overlap
        if set(avoid) & set(buy_months):
            continue

        key = (tuple(sorted(avoid)), tuple(sorted(buy_months)), hold_days)
        if key in seen:
            continue
        seen.add(key)

        n = len(close)
        buy_sig = np.zeros(n, dtype=bool)
        sell_sig = np.zeros(n, dtype=bool)
        months = np.array([d.month for d in dates])

        holding = False
        entry_bar = 0

        for i in range(1, n):
            m = months[i]
            if not holding:
                if m in buy_months and m not in avoid:
                    buy_sig[i] = True
                    holding = True
                    entry_bar = i
            else:
                if (i - entry_bar) >= hold_days or m in avoid:
                    sell_sig[i] = True
                    holding = False

        params = f"avoid={avoid},buy={buy_months},hold={hold_days}"
        results.append(_eval_strategy(close, buy_sig, sell_sig, is_end, "seasonality", params))

        if len(results) >= 308:
            break

    return results


def run_vol_target(close, indicators, is_end):
    """Strategy 9: Volatility targeting."""
    results = []
    for target, v_win, cap, rebal in product(TARGET_VOL, VOL_WIN, LEV_CAP, VOL_REBAL):
        close_is = close[:is_end]
        close_oos = close[is_end:]

        if len(close_is) < MIN_DAYS or len(close_oos) < 60:
            continue

        eq_is, tr_is = simulate_vol_target(close_is, target, v_win, cap, rebal)
        eq_oos, tr_oos = simulate_vol_target(close_oos, target, v_win, cap, rebal)

        m_is = compute_metrics(eq_is, tr_is)
        m_oos = compute_metrics(eq_oos, tr_oos)

        bh_return = close_oos[-1] / close_oos[0] - 1
        total_years = len(close) / 252.0

        params = f"vol={target},win={v_win},cap={cap},rebal={rebal}"
        results.append({
            'strategy': 'vol_target',
            'params': params,
            'is_return': round(m_is['total_return'], 6),
            'is_sharpe': round(m_is['sharpe'], 4),
            'is_maxdd': round(m_is['maxdd'], 4),
            'is_trades': m_is['trades'],
            'oos_return': round(m_oos['total_return'], 6),
            'oos_sharpe': round(m_oos['sharpe'], 4),
            'oos_maxdd': round(m_oos['maxdd'], 4),
            'oos_calmar': round(m_oos['calmar'], 4),
            'oos_trades': m_oos['trades'],
            'bh_return': round(bh_return, 6),
            'vs_bh': round(m_oos['total_return'] - bh_return, 6),
            'years': round(total_years, 2),
            'trades_per_year': round((tr_is + tr_oos) / total_years, 2) if total_years > 0 else 0,
        })

    return results


# ══════════════════════════════════════════════════════════════════════
# Evaluation Helpers
# ══════════════════════════════════════════════════════════════════════

def _eval_strategy(close, buy_sig, sell_sig, is_end, strategy_name, params):
    """Run IS/OOS simulation and return result dict."""
    close_is = close[:is_end]
    close_oos = close[is_end:]
    buy_is = buy_sig[:is_end]
    sell_is = sell_sig[:is_end]
    buy_oos = buy_sig[is_end:]
    sell_oos = sell_sig[is_end:]

    if len(close_is) < MIN_DAYS or len(close_oos) < 60:
        return None

    eq_is, tr_is = simulate_long_only(close_is, buy_is, sell_is)
    eq_oos, tr_oos = simulate_long_only(close_oos, buy_oos, sell_oos)

    m_is = compute_metrics(eq_is, tr_is)
    m_oos = compute_metrics(eq_oos, tr_oos)

    bh_return = close_oos[-1] / close_oos[0] - 1
    total_years = len(close) / 252.0

    return {
        'strategy': strategy_name,
        'params': params,
        'is_return': round(m_is['total_return'], 6),
        'is_sharpe': round(m_is['sharpe'], 4),
        'is_maxdd': round(m_is['maxdd'], 4),
        'is_trades': m_is['trades'],
        'oos_return': round(m_oos['total_return'], 6),
        'oos_sharpe': round(m_oos['sharpe'], 4),
        'oos_maxdd': round(m_oos['maxdd'], 4),
        'oos_calmar': round(m_oos['calmar'], 4),
        'oos_trades': m_oos['trades'],
        'bh_return': round(bh_return, 6),
        'vs_bh': round(m_oos['total_return'] - bh_return, 6),
        'years': round(total_years, 2),
        'trades_per_year': round((tr_is + tr_oos) / total_years, 2) if total_years > 0 else 0,
    }


def _eval_strategy_from_eq(close, eq_full, trades_full, is_end, strategy_name, params):
    """Evaluate from full equity curve, splitting IS/OOS."""
    eq_is = eq_full[:is_end]
    eq_oos = eq_full[is_end:]
    close_oos = close[is_end:]

    if len(eq_is) < MIN_DAYS or len(eq_oos) < 60:
        return None

    # Approximate IS/OOS trade split (50/50)
    tr_is = trades_full // 2
    tr_oos = trades_full - tr_is

    m_is = compute_metrics(eq_is, tr_is)
    m_oos = compute_metrics(eq_oos, tr_oos)

    bh_return = close_oos[-1] / close_oos[0] - 1
    total_years = len(close) / 252.0

    return {
        'strategy': strategy_name,
        'params': params,
        'is_return': round(m_is['total_return'], 6),
        'is_sharpe': round(m_is['sharpe'], 4),
        'is_maxdd': round(m_is['maxdd'], 4),
        'is_trades': m_is['trades'],
        'oos_return': round(m_oos['total_return'], 6),
        'oos_sharpe': round(m_oos['sharpe'], 4),
        'oos_maxdd': round(m_oos['maxdd'], 4),
        'oos_calmar': round(m_oos['calmar'], 4),
        'oos_trades': m_oos['trades'],
        'bh_return': round(bh_return, 6),
        'vs_bh': round(m_oos['total_return'] - bh_return, 6),
        'years': round(total_years, 2),
        'trades_per_year': round(trades_full / total_years, 2) if total_years > 0 else 0,
    }


# ══════════════════════════════════════════════════════════════════════
# Worker Function (per symbol)
# ══════════════════════════════════════════════════════════════════════

def process_symbol(args):
    """Process all 9 strategies x parameter grids for a single symbol."""
    sym, close, high, low, dates = args
    n = len(close)
    is_end = int(n * 0.7)

    if n < MIN_DAYS or is_end < MIN_DAYS or (n - is_end) < 60:
        return []

    # ── Precompute all indicators ──
    indicators = {
        'rsi': {},
        'bb': {},
        'ema': {},
        'sma': {},
        'atr': {},
        'macd': {},
    }

    # RSI for all needed periods
    all_rsi_periods = sorted(set(
        list(RSI_WIN_BB) + list(RSI_WIN_SOLO) + list(DCA_RSI_PERIOD) + [14]
    ))
    for p in all_rsi_periods:
        indicators['rsi'][p] = compute_rsi(close, p)

    # Bollinger Bands
    for bb_win in BB_WIN:
        for bb_std in BB_STD:
            indicators['bb'][(bb_win, bb_std)] = compute_bb(close, bb_win, bb_std)

    # EMA
    for ema_win in EMA_WIN:
        indicators['ema'][ema_win] = compute_ema(close, ema_win)

    # SMA
    for sma_win in [200]:
        indicators['sma'][sma_win] = compute_sma(close, sma_win)

    # ATR
    for atr_win in ATR_WIN:
        indicators['atr'][atr_win] = compute_atr(high, low, close, atr_win)

    # MACD
    for fast, slow, signal in product(MACD_FAST, MACD_SLOW, MACD_SIGNAL):
        if fast < slow:
            indicators['macd'][(fast, slow, signal)] = compute_macd(close, fast, slow, signal)

    # ── Run all 9 strategies ──
    results = []

    # 1. BB+RSI+EMA
    for r in run_bb_rsi_ema(close, indicators, is_end):
        if r is not None:
            r['symbol'] = sym
            results.append(r)

    # 2. RSI solo
    for r in run_rsi_solo(close, indicators, is_end):
        if r is not None:
            r['symbol'] = sym
            results.append(r)

    # 3. DCA
    for r in run_dca(close, indicators, is_end):
        if r is not None:
            r['symbol'] = sym
            results.append(r)

    # 4. Trailing stop
    for r in run_trailing_stop(close, high, low, indicators, is_end):
        if r is not None:
            r['symbol'] = sym
            results.append(r)

    # 5. Momentum
    for r in run_momentum(close, indicators, is_end):
        if r is not None:
            r['symbol'] = sym
            results.append(r)

    # 6. MACD
    for r in run_macd(close, indicators, is_end):
        if r is not None:
            r['symbol'] = sym
            results.append(r)

    # 7. Multi-timeframe
    for r in run_multi_timeframe(close, indicators, is_end):
        if r is not None:
            r['symbol'] = sym
            results.append(r)

    # 8. Seasonality
    for r in run_seasonality(close, dates, is_end):
        if r is not None:
            r['symbol'] = sym
            results.append(r)

    # 9. Volatility targeting
    for r in run_vol_target(close, indicators, is_end):
        if r is not None:
            r['symbol'] = sym
            results.append(r)

    return results


# ══════════════════════════════════════════════════════════════════════
# Data Loading
# ══════════════════════════════════════════════════════════════════════

def load_energy_symbols():
    """Load energy symbol parquet files."""
    symbols = {}
    for sym in ENERGY:
        fpath = DATA_DIR / f"{sym}.parquet"
        if not fpath.exists():
            print(f"  Skip {sym}: file not found")
            continue
        df = pd.read_parquet(fpath)
        if len(df) < MIN_DAYS:
            print(f"  Skip {sym}: only {len(df)} days")
            continue

        close = df["close"].values.astype(np.float64)
        high = df["high"].values.astype(np.float64) if "high" in df.columns else close.copy()
        low = df["low"].values.astype(np.float64) if "low" in df.columns else close.copy()
        dates = df.index.to_pydatetime() if hasattr(df.index, 'to_pydatetime') else pd.to_datetime(df.index).to_pydatetime()

        symbols[sym] = (close, high, low, dates)

    return symbols


# ══════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════

def main():
    t0 = time.time()
    print("=" * 70)
    print("Energy Sector 9-Strategy Backtest")
    print("=" * 70)

    # Load data
    print("\n[1/3] Loading energy symbols...")
    symbols = load_energy_symbols()
    print(f"  Loaded {len(symbols)} symbols: {list(symbols.keys())}")

    if not symbols:
        print("No symbols found. Check data/ directory.")
        return

    # Estimate total combinations
    n_bb_rsi = len(BB_WIN) * len(BB_STD) * len(RSI_WIN_BB) * len(RSI_BUY_BB) * len(RSI_SELL_BB) * len(EMA_WIN) * len(EMA_FILTER)
    n_rsi = len(RSI_WIN_SOLO) * len(OVERSOLD) * len(OVERBOUGHT) * len(RSI_EXIT)
    # oversold < overbought filter reduces this
    n_rsi_filtered = sum(1 for o, ob in product(OVERSOLD, OVERBOUGHT) if o < ob) * len(RSI_WIN_SOLO) * len(RSI_EXIT)
    n_dca = len(DCA_FREQ) * len(DCA_RSI_SCHEME) * len(DCA_RSI_PERIOD) * len(DCA_BOOST)
    n_trail = len(ATR_WIN) * len(ATR_MULT) + len(TRAIL_PCT)  # ATR combos + fixed combos
    n_mom = len(MOM_LOOKBACK) * len(MOM_THRESHOLD) * len(MOM_HOLD)
    n_macd_raw = len(MACD_FAST) * len(MACD_SLOW) * len(MACD_SIGNAL) * len(MACD_FILTER)
    n_macd = sum(1 for f, s in product(MACD_FAST, MACD_SLOW) if f < s) * len(MACD_SIGNAL) * len(MACD_FILTER)
    n_mtf = len(MTF_WEEKLY_RSI_BUY) * len(MTF_DAILY_STRATEGY) * len(MTF_WEEKLY_BB_FILTER)
    n_season = 308  # capped
    n_vol = len(TARGET_VOL) * len(VOL_WIN) * len(LEV_CAP) * len(VOL_REBAL)

    combos_per_sym = n_bb_rsi + n_rsi_filtered + n_dca + n_trail + n_mom + n_macd + n_mtf + n_season + n_vol
    total_combos = combos_per_sym * len(symbols)

    print(f"\n  Combos per symbol: ~{combos_per_sym:,}")
    print(f"    1.BB+RSI+EMA: {n_bb_rsi:,}")
    print(f"    2.RSI solo:   {n_rsi_filtered:,}")
    print(f"    3.DCA:        {n_dca:,}")
    print(f"    4.Trail stop: {n_trail:,}")
    print(f"    5.Momentum:   {n_mom:,}")
    print(f"    6.MACD:       {n_macd:,}")
    print(f"    7.Multi-TF:   {n_mtf:,}")
    print(f"    8.Seasonality:~{n_season:,}")
    print(f"    9.Vol target: {n_vol:,}")
    print(f"  Total: ~{total_combos:,}")

    # Prepare worker args
    print("\n[2/3] Running grid search...")
    worker_args = []
    for sym, (close, high, low, dates) in symbols.items():
        worker_args.append((sym, close, high, low, dates))

    n_workers = max(1, cpu_count() - 1)
    print(f"  Using {n_workers} workers")

    all_results = []
    done = 0
    progress_interval = 1  # report per symbol (only 15 symbols)

    with Pool(n_workers) as pool:
        for result_batch in pool.imap_unordered(process_symbol, worker_args):
            all_results.extend(result_batch)
            done += 1
            elapsed = time.time() - t0
            print(f"  [{done}/{len(worker_args)}] {len(all_results):,} results "
                  f"[{elapsed:.1f}s]")
            # Also print progress every 50k results
            if len(all_results) % 50000 < len(result_batch):
                print(f"    ... {len(all_results):,} total results so far")

    # Save results
    print(f"\n[3/3] Saving {len(all_results):,} results...")
    df = pd.DataFrame(all_results)

    # Reorder columns
    col_order = [
        'symbol', 'strategy', 'params',
        'is_return', 'is_sharpe', 'is_maxdd', 'is_trades',
        'oos_return', 'oos_sharpe', 'oos_maxdd', 'oos_calmar', 'oos_trades',
        'bh_return', 'vs_bh', 'years', 'trades_per_year',
    ]
    existing_cols = [c for c in col_order if c in df.columns]
    df = df[existing_cols]

    out_path = RESULTS_DIR / "energy_strategies_results.csv"
    df.to_csv(out_path, index=False)
    print(f"  Saved to {out_path}")

    # ── Summary ──
    elapsed = time.time() - t0
    print(f"\n{'=' * 70}")
    print(f"Completed in {elapsed:.1f}s  ({len(all_results):,} results)")
    print(f"{'=' * 70}")

    if df.empty:
        print("No results generated.")
        return

    # Top 20 by OOS Sharpe
    print(f"\n{'=' * 70}")
    print("TOP 20 by OOS Sharpe")
    print(f"{'=' * 70}")
    top_sharpe = df.nlargest(20, "oos_sharpe")
    display_cols = [c for c in [
        'symbol', 'strategy', 'params',
        'oos_return', 'oos_sharpe', 'oos_maxdd', 'oos_calmar', 'oos_trades',
        'bh_return', 'vs_bh', 'years', 'trades_per_year',
    ] if c in df.columns]
    print(top_sharpe[display_cols].to_string(index=False))

    # Top 20 by OOS Calmar
    print(f"\n{'=' * 70}")
    print("TOP 20 by OOS Calmar")
    print(f"{'=' * 70}")
    top_calmar = df.nlargest(20, "oos_calmar")
    print(top_calmar[display_cols].to_string(index=False))

    # Strategy breakdown
    print(f"\n{'=' * 70}")
    print("STRATEGY BREAKDOWN (mean OOS Sharpe)")
    print(f"{'=' * 70}")
    strat_stats = df.groupby("strategy").agg(
        count=("oos_sharpe", "count"),
        mean_sharpe=("oos_sharpe", "mean"),
        max_sharpe=("oos_sharpe", "max"),
        mean_return=("oos_return", "mean"),
        mean_maxdd=("oos_maxdd", "mean"),
        pct_beat_bh=("vs_bh", lambda x: (x > 0).mean()),
    ).sort_values("mean_sharpe", ascending=False)
    print(strat_stats.to_string())

    # Best strategy per symbol
    print(f"\n{'=' * 70}")
    print("BEST STRATEGY PER SYMBOL (by OOS Sharpe)")
    print(f"{'=' * 70}")
    best_per_sym = df.loc[df.groupby("symbol")["oos_sharpe"].idxmax()]
    for _, row in best_per_sym.iterrows():
        print(f"  {row['symbol']:6s} | {row['strategy']:15s} | "
              f"Sharpe={row['oos_sharpe']:.3f} | "
              f"Return={row['oos_return']:.4f} | "
              f"MaxDD={row['oos_maxdd']:.4f} | "
              f"vs_BH={row['vs_bh']:+.4f}")

    print(f"\nDone. Results: {out_path}")


if __name__ == "__main__":
    main()
