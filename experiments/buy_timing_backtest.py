"""
Buy-Timing Strategy Backtest
- No selling — buy and hold until the last day
- Total investment: $2,000 for all strategies
- Only difference: WHEN to buy
"""
import pandas as pd
import numpy as np

# Load data
df = pd.read_parquet("data/SOXL.parquet")
df = df.sort_index()
df["ret"] = df["close"].pct_change()

TOTAL_CASH = 2000.0

# ── Indicator helpers ──
def rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def bollinger(series, period=20, num_std=2):
    sma = series.rolling(period).mean()
    std = series.rolling(period).std()
    upper = sma + num_std * std
    lower = sma - num_std * std
    return sma, upper, lower

# Pre-compute indicators
df["rsi14"] = rsi(df["close"], 14)
df["sma50"] = df["close"].rolling(50).mean()
df["sma200"] = df["close"].rolling(200).mean()
bb_mid, bb_upper, bb_lower = bollinger(df["close"], 20, 2)
df["bb_mid"] = bb_mid
df["bb_upper"] = bb_upper
df["bb_lower"] = bb_lower

# Consecutive down days
consec = []
count = 0
for r in df["ret"]:
    if r < 0:
        count += 1
    else:
        count = 0
    consec.append(count)
df["consec_down"] = consec

final_price = df["close"].iloc[-1]

# ── Generic backtest function ──
def backtest(signal_mask, name):
    """
    signal_mask: boolean Series aligned with df index, True = buy day
    Equally distributes $2000 across all buy days.
    """
    buy_days = df.loc[signal_mask]
    n_buys = len(buy_days)
    if n_buys == 0:
        return {"strategy": name, "n_buys": 0, "final_value": TOTAL_CASH,
                "return_pct": 0, "avg_buy_price": None, "max_dd": None, "sharpe": None}

    per_buy = TOTAL_CASH / n_buys
    shares_each = per_buy / buy_days["close"]
    total_shares = shares_each.sum()
    avg_buy_price = TOTAL_CASH / total_shares
    final_value = total_shares * final_price
    ret_pct = (final_value / TOTAL_CASH - 1) * 100

    # Compute portfolio value over time for MaxDD and Sharpe
    # cumulative shares over time
    shares_cum = pd.Series(0.0, index=df.index)
    cash_spent_cum = pd.Series(0.0, index=df.index)
    for date in buy_days.index:
        shares_cum.loc[date:] += shares_each.loc[date]
        cash_spent_cum.loc[date:] += per_buy

    # Only compute from first buy onwards
    first_buy = buy_days.index[0]
    mask = df.index >= first_buy
    port_value = shares_cum[mask] * df["close"][mask]
    # We invested cash_spent_cum, so total value = port_value + (TOTAL_CASH - cash_spent_cum)
    # But since we distribute equally, remaining cash = TOTAL_CASH - cash_spent_cum
    total_value = port_value + (TOTAL_CASH - cash_spent_cum[mask])

    # Max drawdown
    peak = total_value.cummax()
    dd = (total_value - peak) / peak
    max_dd = dd.min() * 100

    # Sharpe (daily returns of portfolio)
    daily_ret = total_value.pct_change().dropna()
    if len(daily_ret) > 1 and daily_ret.std() > 0:
        sharpe = daily_ret.mean() / daily_ret.std() * np.sqrt(252)
    else:
        sharpe = 0.0

    return {
        "strategy": name,
        "n_buys": n_buys,
        "final_value": round(final_value, 2),
        "return_pct": round(ret_pct, 2),
        "avg_buy_price": round(avg_buy_price, 4),
        "max_dd": round(max_dd, 2),
        "sharpe": round(sharpe, 3),
    }

# ══════════════════════════════════════
# BASELINE STRATEGIES
# ══════════════════════════════════════

# 0a. Buy & Hold (lump sum day 1)
first_day_mask = pd.Series(False, index=df.index)
first_day_mask.iloc[0] = True

# 0b. Monthly DCA (buy on first trading day of each month)
monthly_mask = ~df.index.to_period("M").duplicated()

results = []
results.append(backtest(first_day_mask, "0. Buy & Hold (Lump Sum)"))
results.append(backtest(monthly_mask, "0. Monthly DCA"))

# ══════════════════════════════════════
# STRATEGY 1: Dip-Buy DCA
# Buy only on days with >= N% drop from previous day
# ══════════════════════════════════════
for pct in [1, 2, 3, 5]:
    mask = df["ret"] <= -pct/100
    results.append(backtest(mask, f"1. Dip Buy (>={pct}% drop)"))

# ══════════════════════════════════════
# STRATEGY 2: RSI Oversold
# ══════════════════════════════════════
for threshold in [30, 25, 20]:
    mask = df["rsi14"] < threshold
    results.append(backtest(mask, f"2. RSI < {threshold}"))

# ══════════════════════════════════════
# STRATEGY 3: Bollinger Band Lower Touch
# ══════════════════════════════════════
mask_bb = df["close"] <= df["bb_lower"]
results.append(backtest(mask_bb, "3. BB Lower Touch"))

# Also: close below BB lower by 1 std more
mask_bb_deep = df["close"] <= (df["bb_lower"] - df["close"].rolling(20).std())
results.append(backtest(mask_bb_deep, "3. BB Deep Lower"))

# ══════════════════════════════════════
# STRATEGY 4: Below SMA(50) — "undervalued" zone
# ══════════════════════════════════════
mask_sma50 = df["close"] < df["sma50"]
results.append(backtest(mask_sma50, "4. Below SMA50"))

mask_sma200 = df["close"] < df["sma200"]
results.append(backtest(mask_sma200, "4. Below SMA200"))

# ══════════════════════════════════════
# STRATEGY 5: Consecutive Down Days
# ══════════════════════════════════════
for n in [2, 3, 5]:
    mask = df["consec_down"] >= n
    results.append(backtest(mask, f"5. {n}+ Consec Down"))

# ══════════════════════════════════════
# STRATEGY 6: Combo — RSI < 40 AND Close < BB Mid
# ══════════════════════════════════════
mask_combo1 = (df["rsi14"] < 40) & (df["close"] < df["bb_mid"])
results.append(backtest(mask_combo1, "6. RSI<40 & <BB_Mid"))

mask_combo2 = (df["rsi14"] < 30) & (df["close"] <= df["bb_lower"])
results.append(backtest(mask_combo2, "6. RSI<30 & BB_Lower"))

# ══════════════════════════════════════
# STRATEGY 7: Golden Cross Zone — buy when SMA50 < SMA200 (death cross = cheap zone)
# ══════════════════════════════════════
mask_death = (df["sma50"] < df["sma200"]) & df["sma200"].notna()
results.append(backtest(mask_death, "7. Death Cross Zone"))

# ══════════════════════════════════════
# STRATEGY 8: Volatility Spike — buy when daily |return| > 2 std of 20-day vol
# ══════════════════════════════════════
vol20 = df["ret"].rolling(20).std()
mask_vol = (df["ret"] < 0) & (df["ret"].abs() > 2 * vol20)
results.append(backtest(mask_vol, "8. Vol Spike (drop>2σ)"))

# ══════════════════════════════════════
# STRATEGY 9: Mean-Reversion Combo — RSI<35 AND 2+ consec down AND below SMA50
# ══════════════════════════════════════
mask_mr = (df["rsi14"] < 35) & (df["consec_down"] >= 2) & (df["close"] < df["sma50"])
results.append(backtest(mask_mr, "9. MeanRev Combo"))

# ══════════════════════════════════════
# Print results table
# ══════════════════════════════════════
res_df = pd.DataFrame(results)
res_df = res_df.sort_values("return_pct", ascending=False).reset_index(drop=True)
print("\n" + "="*100)
print(f"SOXL Buy-Timing Strategy Backtest Results  |  Period: {df.index[0].date()} ~ {df.index[-1].date()}  |  Investment: ${TOTAL_CASH:,.0f}")
print(f"Final SOXL Price: ${final_price:.2f}")
print("="*100)
print(f"{'#':<3} {'Strategy':<28} {'Buys':>6} {'Avg Price':>10} {'Final $':>12} {'Return%':>10} {'MaxDD%':>8} {'Sharpe':>8}")
print("-"*100)
for _, r in res_df.iterrows():
    avg = f"${r['avg_buy_price']:.2f}" if r['avg_buy_price'] else "N/A"
    print(f"{_:<3} {r['strategy']:<28} {r['n_buys']:>6} {avg:>10} {r['final_value']:>12,.2f} {r['return_pct']:>9.1f}% {r['max_dd']:>7.1f}% {r['sharpe']:>8.3f}")
print("="*100)
