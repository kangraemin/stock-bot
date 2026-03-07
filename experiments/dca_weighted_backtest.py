"""
DCA + RSI 가중치 전략 백테스트
- 매월 기본 매수 (DCA)
- RSI에 따라 매수 가중치 조절
- RSI 높으면 일부 매도
- 레버리지 ETF 중심
"""
import sys
import pandas as pd
import numpy as np
import os
import time

TOTAL_CASH = 2000.0
FEE_RATE = 0.0025

def rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def bollinger_upper(series, period=20, num_std=2):
    sma = series.rolling(period).mean()
    std = series.rolling(period).std()
    return sma + num_std * std

def prepare_data(symbol):
    df = pd.read_parquet(f"data/{symbol}.parquet")
    df = df.sort_index()
    df["rsi14"] = rsi(df["close"], 14)
    df["sma200"] = df["close"].rolling(200).mean()
    df["bb_upper"] = bollinger_upper(df["close"], 20, 2)
    return df


def run_dca_weighted(df, buy_boost_rsi, buy_boost_mult, sell_rsi, sell_pct, monthly_budget=None):
    """
    매월 첫 거래일에 기본 매수 (DCA)
    - RSI < buy_boost_rsi → 매수액 * buy_boost_mult
    - RSI > sell_rsi → 보유 주식의 sell_pct% 매도
    - sell_pct=0이면 매수 스킵만 (매도 안 함)

    monthly_budget: None이면 TOTAL_CASH/총월수로 균등 배분
    """
    months = df.index.to_period("M")
    unique_months = months.unique()
    n_months = len(unique_months)

    if monthly_budget is None:
        monthly_budget = TOTAL_CASH / n_months

    cash = TOTAL_CASH
    shares = 0.0
    n_buys = 0
    n_sells = 0
    n_skips = 0
    total_invested = 0.0

    peak_val = TOTAL_CASH
    max_dd = 0.0

    close = df["close"].values
    rsi_arr = df["rsi14"].values
    bb_upper = df["bb_upper"].values
    month_arr = months.values

    prev_month = None

    for i in range(len(df)):
        cur_month = month_arr[i]
        price = close[i]
        rv = rsi_arr[i]

        is_month_start = (cur_month != prev_month)
        prev_month = cur_month

        if is_month_start and not np.isnan(rv):
            # Monthly DCA logic
            if rv > sell_rsi and sell_pct > 0 and shares > 0:
                # Sell portion
                sell_shares = shares * sell_pct / 100.0
                proceeds = sell_shares * price * (1 - FEE_RATE)
                shares -= sell_shares
                cash += proceeds
                n_sells += 1
            elif rv < buy_boost_rsi:
                # Boosted buy
                buy_amount = min(monthly_budget * buy_boost_mult, cash)
                if buy_amount > 1:
                    new_shares = buy_amount * (1 - FEE_RATE) / price
                    shares += new_shares
                    cash -= buy_amount
                    total_invested += buy_amount
                    n_buys += 1
            elif rv <= sell_rsi:
                # Normal buy
                buy_amount = min(monthly_budget, cash)
                if buy_amount > 1:
                    new_shares = buy_amount * (1 - FEE_RATE) / price
                    shares += new_shares
                    cash -= buy_amount
                    total_invested += buy_amount
                    n_buys += 1
            else:
                # RSI high but no sell → skip
                n_skips += 1

        val = cash + shares * price
        if val > peak_val:
            peak_val = val
        dd = (val - peak_val) / peak_val
        if dd < max_dd:
            max_dd = dd

    final = cash + shares * close[-1]
    ret = (final / TOTAL_CASH - 1) * 100

    return {
        "n_buys": n_buys,
        "n_sells": n_sells,
        "n_skips": n_skips,
        "final_value": round(final, 2),
        "return_pct": round(ret, 1),
        "max_dd_pct": round(max_dd * 100, 1),
    }


def run_baseline_bh(df):
    price0 = df["close"].iloc[0]
    shares = TOTAL_CASH * (1 - FEE_RATE) / price0
    final = shares * df["close"].iloc[-1]
    return round((final / TOTAL_CASH - 1) * 100, 1)

def run_baseline_dca(df):
    months = df.index.to_period("M")
    unique_months = months.unique()
    n_months = len(unique_months)
    monthly = TOTAL_CASH / n_months
    cash = TOTAL_CASH
    shares = 0.0
    prev_month = None
    for i in range(len(df)):
        if months.values[i] != prev_month:
            prev_month = months.values[i]
            buy_amount = min(monthly, cash)
            if buy_amount > 1:
                shares += buy_amount * (1 - FEE_RATE) / df["close"].iloc[i]
                cash -= buy_amount
    final = cash + shares * df["close"].iloc[-1]
    return round((final / TOTAL_CASH - 1) * 100, 1)


# ── Grid ──
symbols = ["SOXL", "TQQQ", "SPXL", "TNA", "UPRO", "QLD", "UWM", "ROM",
           "SPY", "QQQ", "IWM", "AAPL", "NVDA", "MSFT", "TSLA"]
symbols = [s for s in symbols if os.path.exists(f"data/{s}.parquet")]

buy_boost_rsi_vals = [25, 30, 35, 40, 45]
buy_boost_mult_vals = [1.5, 2.0, 3.0, 5.0]
sell_rsi_vals = [60, 65, 70, 75, 80, 999]  # 999 = never sell
sell_pct_vals = [0, 20, 30, 50, 80, 100]

combos = []
for bbr in buy_boost_rsi_vals:
    for bbm in buy_boost_mult_vals:
        for sr in sell_rsi_vals:
            for sp in sell_pct_vals:
                if sr == 999 and sp > 0:  # never sell but sell_pct > 0 makes no sense
                    continue
                if sr < 999 and sp == 0:  # sell RSI set but sell nothing
                    combos.append((bbr, bbm, sr, sp))  # just skip buy
                else:
                    combos.append((bbr, bbm, sr, sp))

# Deduplicate
combos = list(set(combos))
combos.sort()

print(f"Symbols: {len(symbols)}", flush=True)
print(f"Combos per symbol: {len(combos)}", flush=True)
print(f"Total: {len(combos) * len(symbols):,}", flush=True)

os.makedirs("results", exist_ok=True)
all_results = []
start = time.time()

for si, symbol in enumerate(symbols):
    t0 = time.time()
    df = prepare_data(symbol)
    bh_ret = run_baseline_bh(df)
    dca_ret = run_baseline_dca(df)
    n_months = len(df.index.to_period("M").unique())

    best_ret = -999
    best_row = None

    for bbr, bbm, sr, sp in combos:
        r = run_dca_weighted(df, bbr, bbm, sr, sp)
        r.update({
            "symbol": symbol,
            "buy_boost_rsi": bbr,
            "buy_boost_mult": bbm,
            "sell_rsi": sr if sr < 999 else "never",
            "sell_pct": sp,
            "bh_return_pct": bh_ret,
            "dca_return_pct": dca_ret,
            "vs_bh": round(r["return_pct"] - bh_ret, 1),
            "vs_dca": round(r["return_pct"] - dca_ret, 1),
        })
        all_results.append(r)
        if r["return_pct"] > best_ret:
            best_ret = r["return_pct"]
            best_row = r

    elapsed = time.time() - t0
    print(f"[{si+1}/{len(symbols)}] {symbol:>6} | {n_months:>3}mo | "
          f"B&H: {bh_ret:>10,.1f}% | DCA: {dca_ret:>8,.1f}% | "
          f"Best: {best_ret:>10,.1f}% ({best_row['n_buys']}B/{best_row['n_sells']}S/{best_row['n_skips']}skip) | "
          f"vs DCA: {best_row['vs_dca']:>+8,.1f}% | {elapsed:.1f}s", flush=True)

total_elapsed = time.time() - start
print(f"\nDone: {len(all_results):,} in {total_elapsed:.0f}s", flush=True)

res_df = pd.DataFrame(all_results)
res_df.to_csv("results/dca_weighted_grid.csv", index=False)
print(f"Saved: results/dca_weighted_grid.csv", flush=True)

# ── Summary ──
print(f"\n{'='*140}")
print(f"BEST PER SYMBOL")
print(f"{'='*140}")
print(f"{'Sym':<6} {'B':>4} {'S':>4} {'Skip':>4} {'BoostRSI':>8} {'Mult':>5} {'SellRSI':>7} {'Sell%':>5} "
      f"{'Return%':>10} {'B&H%':>10} {'DCA%':>10} {'vs B&H':>10} {'vs DCA':>10} {'MaxDD%':>7}")
print("-"*140)

best_per_sym = res_df.loc[res_df.groupby("symbol")["return_pct"].idxmax()]
best_per_sym = best_per_sym.sort_values("vs_dca", ascending=False)

for _, r in best_per_sym.iterrows():
    print(f"{r['symbol']:<6} {r['n_buys']:>4} {r['n_sells']:>4} {r['n_skips']:>4} "
          f"{r['buy_boost_rsi']:>8} {r['buy_boost_mult']:>5.1f} {str(r['sell_rsi']):>7} {r['sell_pct']:>5} "
          f"{r['return_pct']:>9,.1f}% {r['bh_return_pct']:>9,.1f}% {r['dca_return_pct']:>9,.1f}% "
          f"{r['vs_bh']:>+9,.1f}% {r['vs_dca']:>+9,.1f}% {r['max_dd_pct']:>6.1f}%")

# ── Best with sells (active management) ──
print(f"\n{'='*140}")
print(f"BEST WITH ACTIVE SELLING (sell_pct > 0, sell_rsi < 999)")
print(f"{'='*140}")
active = res_df[(res_df["sell_pct"] > 0) & (res_df["sell_rsi"] != "never")]
best_active = active.loc[active.groupby("symbol")["return_pct"].idxmax()]
best_active = best_active.sort_values("vs_dca", ascending=False)

print(f"{'Sym':<6} {'B':>4} {'S':>4} {'Skip':>4} {'BoostRSI':>8} {'Mult':>5} {'SellRSI':>7} {'Sell%':>5} "
      f"{'Return%':>10} {'B&H%':>10} {'DCA%':>10} {'vs B&H':>10} {'vs DCA':>10} {'MaxDD%':>7}")
print("-"*140)
for _, r in best_active.iterrows():
    print(f"{r['symbol']:<6} {r['n_buys']:>4} {r['n_sells']:>4} {r['n_skips']:>4} "
          f"{r['buy_boost_rsi']:>8} {r['buy_boost_mult']:>5.1f} {str(r['sell_rsi']):>7} {r['sell_pct']:>5} "
          f"{r['return_pct']:>9,.1f}% {r['bh_return_pct']:>9,.1f}% {r['dca_return_pct']:>9,.1f}% "
          f"{r['vs_bh']:>+9,.1f}% {r['vs_dca']:>+9,.1f}% {r['max_dd_pct']:>6.1f}%")

# ── Stats ──
print(f"\n*** OVERALL STATS ***")
for sym in symbols:
    sub = res_df[res_df["symbol"] == sym]
    dca_ret = sub["dca_return_pct"].iloc[0]
    beat_dca = len(sub[sub["return_pct"] > dca_ret])
    beat_bh = len(sub[sub["return_pct"] > sub["bh_return_pct"]])
    print(f"  {sym:>6}: beat DCA {beat_dca:>4}/{len(sub)} ({beat_dca/len(sub)*100:>5.1f}%) | "
          f"beat B&H {beat_bh:>4}/{len(sub)} ({beat_bh/len(sub)*100:>5.1f}%)", flush=True)
