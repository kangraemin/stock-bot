"""
Combined Buy-Timing + Sell-Timing Greedy Grid Search
- 넓은 파라미터 범위, 다양한 매수/매도 전략 조합
- 결과 CSV 저장
"""
import pandas as pd
import numpy as np
from itertools import product
import os
import time

# Load data
df = pd.read_parquet("data/SOXL.parquet")
df = df.sort_index()
df["ret"] = df["close"].pct_change()

TOTAL_CASH = 2000.0
FEE_RATE = 0.0025  # 0.25% per trade

# ── Indicators ──
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
    return sma, sma + num_std * std, sma - num_std * std

df["rsi14"] = rsi(df["close"], 14)
df["sma50"] = df["close"].rolling(50).mean()
df["sma200"] = df["close"].rolling(200).mean()
bb_mid, bb_upper, bb_lower = bollinger(df["close"], 20, 2)
df["bb_mid"] = bb_mid
df["bb_upper"] = bb_upper
df["bb_lower"] = bb_lower

consec = []
count = 0
for r in df["ret"]:
    if r < 0:
        count += 1
    else:
        count = 0
    consec.append(count)
df["consec_down"] = consec

# Pre-convert to numpy for speed
close = df["close"].values
rsi_arr = df["rsi14"].values
sma50_arr = df["sma50"].values
sma200_arr = df["sma200"].values
bb_mid_arr = df["bb_mid"].values
bb_lower_arr = df["bb_lower"].values
bb_upper_arr = df["bb_upper"].values
consec_arr = df["consec_down"].values
ret_arr = df["ret"].values
n_bars = len(df)


# ── Fast numpy-based backtest ──
def run_combined_fast(buy_type, buy_rsi,
                      sell_rsi, sell_cond,
                      rebuy_rsi, rebuy_cond):
    cash = TOTAL_CASH
    shares = 0.0
    state = 0  # 0=CASH, 1=HOLDING, 2=WAIT_REBUY
    n_buys = 0
    n_sells = 0
    peak_val = TOTAL_CASH
    max_dd = 0.0

    for i in range(n_bars):
        if np.isnan(sma200_arr[i]) or np.isnan(rsi_arr[i]):
            val = cash + shares * close[i]
            if val > peak_val:
                peak_val = val
            continue

        price = close[i]
        rv = rsi_arr[i]

        if state == 0:  # CASH - check buy
            buy = False
            if buy_type == 0:  # RSI only
                buy = rv < buy_rsi
            elif buy_type == 1:  # RSI + below SMA50
                buy = rv < buy_rsi and price < sma50_arr[i]
            elif buy_type == 2:  # RSI + below SMA200
                buy = rv < buy_rsi and price < sma200_arr[i]
            elif buy_type == 3:  # RSI + BB lower
                buy = rv < buy_rsi and price <= bb_lower_arr[i]
            elif buy_type == 4:  # RSI + consec down 2+
                buy = rv < buy_rsi and consec_arr[i] >= 2
            elif buy_type == 5:  # RSI + consec down 2+ + below SMA50 (MeanRev)
                buy = rv < buy_rsi and consec_arr[i] >= 2 and price < sma50_arr[i]
            elif buy_type == 6:  # RSI + below BB_mid
                buy = rv < buy_rsi and price < bb_mid_arr[i]
            elif buy_type == 7:  # Dip buy (ret <= -X%)
                buy = ret_arr[i] <= -buy_rsi / 100.0  # reuse buy_rsi as dip %
            elif buy_type == 8:  # Below SMA50 (no RSI)
                buy = price < sma50_arr[i]
            elif buy_type == 9:  # Below SMA200 (no RSI)
                buy = price < sma200_arr[i]

            if buy:
                cost = cash * (1 - FEE_RATE)
                shares = cost / price
                cash = 0
                n_buys += 1
                state = 1

        elif state == 1:  # HOLDING - check sell
            sell = False
            if sell_cond == 0:  # RSI only
                sell = rv > sell_rsi
            elif sell_cond == 1:  # RSI + price > SMA200
                sell = rv > sell_rsi and price > sma200_arr[i]
            elif sell_cond == 2:  # RSI + price > SMA50
                sell = rv > sell_rsi and price > sma50_arr[i]
            elif sell_cond == 3:  # RSI + price > BB upper
                sell = rv > sell_rsi and price > bb_upper_arr[i]
            elif sell_cond == 4:  # RSI + price > BB mid
                sell = rv > sell_rsi and price > bb_mid_arr[i]

            if sell:
                cash = shares * price * (1 - FEE_RATE)
                shares = 0
                n_sells += 1
                state = 2

        elif state == 2:  # WAIT_REBUY - check rebuy
            rebuy = False
            if rebuy_cond == 0:  # RSI only
                rebuy = rv < rebuy_rsi
            elif rebuy_cond == 1:  # RSI + below SMA50
                rebuy = rv < rebuy_rsi and price < sma50_arr[i]
            elif rebuy_cond == 2:  # RSI + BB lower
                rebuy = rv < rebuy_rsi and price <= bb_lower_arr[i]
            elif rebuy_cond == 3:  # RSI + below SMA200
                rebuy = rv < rebuy_rsi and price < sma200_arr[i]
            elif rebuy_cond == 4:  # RSI + below BB mid
                rebuy = rv < rebuy_rsi and price < bb_mid_arr[i]
            elif rebuy_cond == 5:  # RSI + consec down 2+
                rebuy = rv < rebuy_rsi and consec_arr[i] >= 2

            if rebuy:
                cost = cash * (1 - FEE_RATE)
                shares = cost / price
                cash = 0
                n_buys += 1
                state = 1

        val = cash + shares * price
        if val > peak_val:
            peak_val = val
        dd = (val - peak_val) / peak_val
        if dd < max_dd:
            max_dd = dd

    final_value = cash + shares * close[-1]
    ret_pct = (final_value / TOTAL_CASH - 1) * 100

    return {
        "n_buys": n_buys,
        "n_sells": n_sells,
        "final_value": round(final_value, 2),
        "return_pct": round(ret_pct, 1),
        "max_dd_pct": round(max_dd * 100, 1),
    }


# ══════════════════════════════════════
# PARAMETER GRID
# ══════════════════════════════════════

buy_type_names = {
    0: "RSI_only",
    1: "RSI+<SMA50",
    2: "RSI+<SMA200",
    3: "RSI+BB_lower",
    4: "RSI+2consec_down",
    5: "MeanRev(RSI+2down+<SMA50)",
    6: "RSI+<BB_mid",
    7: "DipBuy(ret<=-X%)",
    8: "Below_SMA50",
    9: "Below_SMA200",
}

sell_cond_names = {0: "rsi_only", 1: "rsi+>sma200", 2: "rsi+>sma50", 3: "rsi+>bb_upper", 4: "rsi+>bb_mid"}
rebuy_cond_names = {0: "rsi_only", 1: "rsi+<sma50", 2: "rsi+bb_lower", 3: "rsi+<sma200", 4: "rsi+<bb_mid", 5: "rsi+2consec_down"}

# Buy params
buy_types = list(range(10))
buy_rsi_vals = [25, 30, 35, 40, 45, 50, 55]  # for type 7 (dip), this = dip %: reinterpreted as 1,2,3,5
# For dip buy, use different values
dip_vals = [1, 2, 3, 5]

# Sell params
sell_rsi_vals = [55, 60, 65, 70, 75, 80]
sell_conds = list(range(5))

# Rebuy params
rebuy_rsi_vals = [25, 30, 35, 40, 45, 50, 55]
rebuy_conds = list(range(6))

# Build all combos: (buy_type, buy_rsi, sell_rsi, sell_cond, rebuy_rsi, rebuy_cond)
combos = []

# RSI-based buy types (0-6)
for bt in range(7):
    for br in buy_rsi_vals:
        for sr in sell_rsi_vals:
            for sc in sell_conds:
                for rr in rebuy_rsi_vals:
                    for rc in rebuy_conds:
                        if br >= sr:
                            continue
                        combos.append((bt, br, sr, sc, rr, rc))

# Dip buy (type 7)
for dip in dip_vals:
    for sr in sell_rsi_vals:
        for sc in sell_conds:
            for rr in rebuy_rsi_vals:
                for rc in rebuy_conds:
                    combos.append((7, dip, sr, sc, rr, rc))

# No-RSI buy types (8, 9) - below SMA50/200
for bt in [8, 9]:
    for sr in sell_rsi_vals:
        for sc in sell_conds:
            for rr in rebuy_rsi_vals:
                for rc in rebuy_conds:
                    combos.append((bt, 0, sr, sc, rr, rc))

total = len(combos)
print(f"Total combinations: {total:,}")

start = time.time()
results = []

for i, (bt, br, sr, sc, rr, rc) in enumerate(combos):
    if i % 10000 == 0 and i > 0:
        elapsed = time.time() - start
        rate = i / elapsed
        eta = (total - i) / rate
        print(f"  {i:,}/{total:,} ({i/total*100:.0f}%) - {rate:.0f}/s - ETA {eta:.0f}s")

    r = run_combined_fast(bt, br, sr, sc, rr, rc)
    r["buy_type"] = buy_type_names[bt]
    r["buy_rsi"] = br
    r["sell_rsi"] = sr
    r["sell_cond"] = sell_cond_names[sc]
    r["rebuy_rsi"] = rr
    r["rebuy_cond"] = rebuy_cond_names[rc]
    results.append(r)

elapsed = time.time() - start
print(f"\nDone: {total:,} combos in {elapsed:.1f}s ({total/elapsed:.0f}/s)")

# ── Save to CSV ──
res_df = pd.DataFrame(results)
res_df = res_df.sort_values("return_pct", ascending=False).reset_index(drop=True)

# Column order
cols = ["n_buys", "n_sells", "buy_type", "buy_rsi", "sell_rsi", "sell_cond",
        "rebuy_rsi", "rebuy_cond", "final_value", "return_pct", "max_dd_pct"]
res_df = res_df[cols]

os.makedirs("results", exist_ok=True)
csv_path = "results/soxl_combined_timing_grid.csv"
res_df.to_csv(csv_path, index=False)
print(f"\nSaved: {csv_path} ({len(res_df):,} rows)")

# ── B&H baseline ──
bh_shares = TOTAL_CASH * (1 - FEE_RATE) / close[0]
bh_final = bh_shares * close[-1]
bh_ret = (bh_final / TOTAL_CASH - 1) * 100
print(f"\nB&H: ${bh_final:,.0f} ({bh_ret:,.1f}%)")

# ── Summary ──
beat_bh = res_df[res_df["return_pct"] > bh_ret]
print(f"Beat B&H: {len(beat_bh):,} / {len(res_df):,} ({len(beat_bh)/len(res_df)*100:.1f}%)")
print(f"Median return: {res_df['return_pct'].median():,.1f}%")

# ── Top 30 ──
print(f"\n{'='*140}")
print(f"TOP 30 (by return)")
print(f"{'='*140}")
print(f"{'#':<4} {'B':>4} {'S':>4}  {'Buy Type':<28} {'BuyRSI':>6} {'SellRSI':>7} {'SellCond':<14} {'RebuyRSI':>8} {'RebuyCond':<16} {'Final$':>12} {'Ret%':>10} {'MaxDD%':>7}")
print("-"*140)
for i, r in res_df.head(30).iterrows():
    print(f"{i:<4} {r['n_buys']:>4} {r['n_sells']:>4}  {r['buy_type']:<28} {r['buy_rsi']:>6} {r['sell_rsi']:>7} {r['sell_cond']:<14} {r['rebuy_rsi']:>8} {r['rebuy_cond']:<16} {r['final_value']:>12,.0f} {r['return_pct']:>9,.1f}% {r['max_dd_pct']:>6.1f}%")

# ── Top 30 with min 20 trades ──
active = res_df[res_df["n_buys"] >= 20].reset_index(drop=True)
print(f"\n{'='*140}")
print(f"TOP 30 (min 20 trades)")
print(f"{'='*140}")
print(f"{'#':<4} {'B':>4} {'S':>4}  {'Buy Type':<28} {'BuyRSI':>6} {'SellRSI':>7} {'SellCond':<14} {'RebuyRSI':>8} {'RebuyCond':<16} {'Final$':>12} {'Ret%':>10} {'MaxDD%':>7}")
print("-"*140)
for i, r in active.head(30).iterrows():
    print(f"{i:<4} {r['n_buys']:>4} {r['n_sells']:>4}  {r['buy_type']:<28} {r['buy_rsi']:>6} {r['sell_rsi']:>7} {r['sell_cond']:<14} {r['rebuy_rsi']:>8} {r['rebuy_cond']:<16} {r['final_value']:>12,.0f} {r['return_pct']:>9,.1f}% {r['max_dd_pct']:>6.1f}%")

# ── Top 30 with min 50 trades ──
freq = res_df[res_df["n_buys"] >= 50].reset_index(drop=True)
print(f"\n{'='*140}")
print(f"TOP 30 (min 50 trades, ~3+/year)")
print(f"{'='*140}")
print(f"{'#':<4} {'B':>4} {'S':>4}  {'Buy Type':<28} {'BuyRSI':>6} {'SellRSI':>7} {'SellCond':<14} {'RebuyRSI':>8} {'RebuyCond':<16} {'Final$':>12} {'Ret%':>10} {'MaxDD%':>7}")
print("-"*140)
for i, r in freq.head(30).iterrows():
    print(f"{i:<4} {r['n_buys']:>4} {r['n_sells']:>4}  {r['buy_type']:<28} {r['buy_rsi']:>6} {r['sell_rsi']:>7} {r['sell_cond']:<14} {r['rebuy_rsi']:>8} {r['rebuy_cond']:<16} {r['final_value']:>12,.0f} {r['return_pct']:>9,.1f}% {r['max_dd_pct']:>6.1f}%")

# ── Stats by trade frequency ──
print(f"\n*** BY TRADE FREQUENCY ***")
for min_t, label in [(1, "1+"), (10, "10+"), (20, "20+"), (50, "50+"), (100, "100+")]:
    sub = res_df[res_df["n_buys"] >= min_t]
    if len(sub) == 0:
        continue
    beat = len(sub[sub["return_pct"] > bh_ret])
    print(f"  {label:>4} trades: {len(sub):>6,} combos | beat B&H: {beat:>5,} ({beat/len(sub)*100:>5.1f}%) | "
          f"best: {sub['return_pct'].max():>10,.1f}% | median: {sub['return_pct'].median():>8,.1f}%")
