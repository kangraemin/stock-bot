"""
Multi-Symbol Combined Buy+Sell Timing Grid Search
- 38종목 sell-timing grid search 기반
- 레버리지 ETF 중심 + 주요 종목
- 결과 CSV 저장
"""
import sys
import pandas as pd
import numpy as np
from itertools import product
import os
import time
import glob

FEE_RATE = 0.0025
TOTAL_CASH = 2000.0

# Key symbols: leveraged ETFs + indices + big tech
symbols = [
    # 3x Lev
    "SOXL", "TECL", "TNA", "TQQQ", "SPXL", "FNGU", "UPRO",
    # 2x Lev
    "QLD", "SSO", "ROM", "UWM", "USD",
    # Index
    "SPY", "QQQ", "DIA", "IWM",
    # Big Tech
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA",
]
# Filter to available
symbols = [s for s in symbols if os.path.exists(f"data/{s}.parquet")]
print(f"Symbols: {len(symbols)}", flush=True)
print(", ".join(symbols), flush=True)

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


def prepare_data(symbol):
    df = pd.read_parquet(f"data/{symbol}.parquet")
    df = df.sort_index()
    df["rsi14"] = rsi(df["close"], 14)
    df["sma50"] = df["close"].rolling(50).mean()
    df["sma200"] = df["close"].rolling(200).mean()
    _, bb_upper, bb_lower = bollinger(df["close"], 20, 2)
    df["bb_upper"] = bb_upper
    df["bb_lower"] = bb_lower
    df["bb_mid"] = df["close"].rolling(20).mean()
    consec = []
    count = 0
    for r in df["close"].pct_change():
        if pd.notna(r) and r < 0:
            count += 1
        else:
            count = 0
        consec.append(count)
    df["consec_down"] = consec
    return df


def run_backtest(close, rsi_arr, sma50, sma200, bb_upper, bb_mid, bb_lower, consec,
                 buy_type, buy_rsi, sell_rsi, sell_cond, rebuy_rsi, rebuy_cond):
    n = len(close)
    cash = TOTAL_CASH
    shares = 0.0
    state = 0  # 0=CASH, 1=HOLDING, 2=WAIT_REBUY
    n_buys = 0
    n_sells = 0
    peak_val = TOTAL_CASH
    max_dd = 0.0

    for i in range(n):
        if np.isnan(sma200[i]) or np.isnan(rsi_arr[i]):
            val = cash + shares * close[i]
            if val > peak_val: peak_val = val
            continue

        price = close[i]
        rv = rsi_arr[i]

        if state == 0:
            buy = False
            if buy_type == 0:    buy = rv < buy_rsi
            elif buy_type == 1:  buy = rv < buy_rsi and price < sma50[i]
            elif buy_type == 2:  buy = rv < buy_rsi and price < sma200[i]
            elif buy_type == 3:  buy = rv < buy_rsi and price <= bb_lower[i]
            elif buy_type == 4:  buy = rv < buy_rsi and consec[i] >= 2
            elif buy_type == 5:  buy = rv < buy_rsi and consec[i] >= 2 and price < sma50[i]
            elif buy_type == 6:  buy = rv < buy_rsi and price < bb_mid[i]
            if buy:
                shares = cash * (1 - FEE_RATE) / price
                cash = 0; n_buys += 1; state = 1

        elif state == 1:
            sell = False
            if sell_cond == 0:   sell = rv > sell_rsi
            elif sell_cond == 1: sell = rv > sell_rsi and price > sma200[i]
            elif sell_cond == 2: sell = rv > sell_rsi and price > sma50[i]
            elif sell_cond == 3: sell = rv > sell_rsi and price > bb_upper[i]
            elif sell_cond == 4: sell = rv > sell_rsi and price > bb_mid[i]
            if sell:
                cash = shares * price * (1 - FEE_RATE)
                shares = 0; n_sells += 1; state = 2

        elif state == 2:
            rebuy = False
            if rebuy_cond == 0:   rebuy = rv < rebuy_rsi
            elif rebuy_cond == 1: rebuy = rv < rebuy_rsi and price < sma50[i]
            elif rebuy_cond == 2: rebuy = rv < rebuy_rsi and price <= bb_lower[i]
            elif rebuy_cond == 3: rebuy = rv < rebuy_rsi and price < sma200[i]
            elif rebuy_cond == 4: rebuy = rv < rebuy_rsi and price < bb_mid[i]
            elif rebuy_cond == 5: rebuy = rv < rebuy_rsi and consec[i] >= 2
            if rebuy:
                shares = cash * (1 - FEE_RATE) / price
                cash = 0; n_buys += 1; state = 1

        val = cash + shares * price
        if val > peak_val: peak_val = val
        dd = (val - peak_val) / peak_val
        if dd < max_dd: max_dd = dd

    final = cash + shares * close[-1]
    return n_buys, n_sells, round(final, 2), round((final / TOTAL_CASH - 1) * 100, 1), round(max_dd * 100, 1)


# ── Parameter grid (focused) ──
buy_type_names = {0: "RSI_only", 1: "RSI+<SMA50", 2: "RSI+<SMA200", 3: "RSI+BB_lower",
                  4: "RSI+2consec", 5: "MeanRev", 6: "RSI+<BB_mid"}
sell_cond_names = {0: "rsi_only", 1: "rsi+>sma200", 2: "rsi+>sma50", 3: "rsi+>bb_upper", 4: "rsi+>bb_mid"}
rebuy_cond_names = {0: "rsi_only", 1: "rsi+<sma50", 2: "rsi+bb_lower", 3: "rsi+<sma200", 4: "rsi+<bb_mid", 5: "rsi+2consec"}

buy_types = [0, 4, 5, 6]  # top performers
buy_rsi_vals = [25, 30, 35, 40, 45]
sell_rsi_vals = [55, 60, 65, 70, 75, 80]
sell_conds = [0, 1, 3]  # rsi_only, rsi+sma200, rsi+bb_upper
rebuy_rsi_vals = [30, 40, 50, 55]
rebuy_conds = [0, 2, 5]  # rsi_only, bb_lower, 2consec

# Pre-build combos
combos = []
for bt in buy_types:
    for br in buy_rsi_vals:
        for sr in sell_rsi_vals:
            if br >= sr: continue
            for sc in sell_conds:
                for rr in rebuy_rsi_vals:
                    for rc in rebuy_conds:
                        combos.append((bt, br, sr, sc, rr, rc))

print(f"Combos per symbol: {len(combos)}", flush=True)
print(f"Total: {len(combos) * len(symbols):,}", flush=True)

os.makedirs("results", exist_ok=True)
all_results = []
start = time.time()

for si, symbol in enumerate(symbols):
    t0 = time.time()
    try:
        df = prepare_data(symbol)
    except Exception as e:
        print(f"  SKIP {symbol}: {e}")
        continue

    close = df["close"].values
    rsi_arr = df["rsi14"].values
    sma50 = df["sma50"].values
    sma200 = df["sma200"].values
    bb_upper = df["bb_upper"].values
    bb_mid = df["bb_mid"].values
    bb_lower = df["bb_lower"].values
    consec_arr = df["consec_down"].values
    n_bars = len(df)

    # B&H baseline
    bh_shares = TOTAL_CASH * (1 - FEE_RATE) / close[0]
    bh_final = bh_shares * close[-1]
    bh_ret = round((bh_final / TOTAL_CASH - 1) * 100, 1)

    best_ret = -999
    best_row = None
    sym_results = []

    for bt, br, sr, sc, rr, rc in combos:
        nb, ns, fv, ret, mdd = run_backtest(close, rsi_arr, sma50, sma200, bb_upper, bb_mid, bb_lower, consec_arr,
                                             bt, br, sr, sc, rr, rc)
        row = {
            "symbol": symbol,
            "n_buys": nb, "n_sells": ns,
            "buy_type": buy_type_names[bt], "buy_rsi": br,
            "sell_rsi": sr, "sell_cond": sell_cond_names[sc],
            "rebuy_rsi": rr, "rebuy_cond": rebuy_cond_names[rc],
            "final_value": fv, "return_pct": ret, "max_dd_pct": mdd,
            "bh_return_pct": bh_ret, "vs_bh": round(ret - bh_ret, 1),
        }
        sym_results.append(row)
        if ret > best_ret:
            best_ret = ret
            best_row = row

    all_results.extend(sym_results)
    elapsed = time.time() - t0
    beat_bh = sum(1 for r in sym_results if r["return_pct"] > bh_ret)
    print(f"[{si+1}/{len(symbols)}] {symbol:>6} | {n_bars:>5} bars | B&H: {bh_ret:>10,.1f}% | "
          f"Best: {best_ret:>10,.1f}% ({best_row['n_buys']}B/{best_row['n_sells']}S) | "
          f"Beat B&H: {beat_bh}/{len(combos)} ({beat_bh/len(combos)*100:.0f}%) | {elapsed:.1f}s", flush=True)

total_elapsed = time.time() - start
print(f"\nDone: {len(all_results):,} results in {total_elapsed:.0f}s")

# Save full CSV
res_df = pd.DataFrame(all_results)
res_df.to_csv("results/multi_combined_timing_grid.csv", index=False)
print(f"Saved: results/multi_combined_timing_grid.csv")

# ── Summary by symbol ──
print(f"\n{'='*120}")
print(f"SUMMARY BY SYMBOL (best combo per symbol)")
print(f"{'='*120}")
print(f"{'Symbol':<8} {'Group':<12} {'B':>4} {'S':>4} {'BuyType':<14} {'BuyRSI':>6} {'SellRSI':>7} {'SellCond':<13} {'RebuyRSI':>8} {'RebuyCond':<12} {'Return%':>10} {'B&H%':>10} {'vs B&H':>10} {'MaxDD%':>7}")
print("-"*120)

# Group symbols
groups = {
    "3x Lev": ["SOXL", "TECL", "TNA", "TQQQ", "SPXL", "FNGU", "UPRO"],
    "2x Lev": ["QLD", "SSO", "ROM", "UWM", "USD"],
    "Index": ["SPY", "QQQ", "DIA", "IWM", "VOO", "VTI"],
    "Sector": ["SOXX", "XLK"],
    "Big Tech": ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "NFLX", "AVGO"],
    "Other": [],
}
sym_to_group = {}
for g, syms in groups.items():
    for s in syms:
        sym_to_group[s] = g

best_per_sym = res_df.loc[res_df.groupby("symbol")["return_pct"].idxmax()]
best_per_sym = best_per_sym.sort_values("vs_bh", ascending=False)

for _, r in best_per_sym.iterrows():
    grp = sym_to_group.get(r["symbol"], "Other")
    print(f"{r['symbol']:<8} {grp:<12} {r['n_buys']:>4} {r['n_sells']:>4} {r['buy_type']:<14} {r['buy_rsi']:>6} {r['sell_rsi']:>7} {r['sell_cond']:<13} {r['rebuy_rsi']:>8} {r['rebuy_cond']:<12} {r['return_pct']:>9,.1f}% {r['bh_return_pct']:>9,.1f}% {r['vs_bh']:>+9,.1f}% {r['max_dd_pct']:>6.1f}%")

# ── Which symbols benefit most from timing? ──
print(f"\n{'='*80}")
print("SYMBOLS WHERE TIMING BEATS B&H (best combo)")
print(f"{'='*80}")
winners = best_per_sym[best_per_sym["vs_bh"] > 0]
losers = best_per_sym[best_per_sym["vs_bh"] <= 0]
print(f"Timing wins: {len(winners)}/{len(best_per_sym)} symbols")
print(f"\nTop 10 timing advantage:")
for _, r in winners.head(10).iterrows():
    grp = sym_to_group.get(r["symbol"], "Other")
    print(f"  {r['symbol']:<6} ({grp:<10}) vs_bh: {r['vs_bh']:>+10,.1f}%  ({r['n_buys']}B/{r['n_sells']}S)")
print(f"\nBottom 5 (timing worst):")
for _, r in losers.tail(5).iterrows():
    grp = sym_to_group.get(r["symbol"], "Other")
    print(f"  {r['symbol']:<6} ({grp:<10}) vs_bh: {r['vs_bh']:>+10,.1f}%  ({r['n_buys']}B/{r['n_sells']}S)")
