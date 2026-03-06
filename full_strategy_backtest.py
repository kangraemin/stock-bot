"""
4가지 전략 비교 백테스트 + 3x ETF는 현물(1x) 비교
1. 듀얼 모멘텀 회전
2. 변동성 타겟팅
3. SMA 크로스오버
4. 레버리지 회전 (3x/1x/현금)
+ B&H, DCA 베이스라인

레버리지 ETF: SOXL(3x) vs SOXX(1x), TQQQ(3x) vs QQQ(1x), SPXL(3x) vs SPY(1x), TNA(3x) vs IWM(1x)
"""
import sys
import pandas as pd
import numpy as np
import os
import time

TOTAL_CASH = 2000.0
FEE_RATE = 0.0025

def rsi_calc(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def load_symbol(symbol):
    path = f"data/{symbol}.parquet"
    if not os.path.exists(path):
        return None
    df = pd.read_parquet(path).sort_index()
    df["ret"] = df["close"].pct_change()
    df["sma50"] = df["close"].rolling(50).mean()
    df["sma200"] = df["close"].rolling(200).mean()
    df["rsi14"] = rsi_calc(df["close"], 14)
    df["vol20"] = df["ret"].rolling(20).std() * np.sqrt(252)
    # 12-month momentum (252 trading days)
    df["mom12"] = df["close"].pct_change(252)
    # 1-month momentum
    df["mom1"] = df["close"].pct_change(21)
    return df

def compute_metrics(values, cash_start=TOTAL_CASH):
    pv = pd.Series(values) if not isinstance(values, pd.Series) else values
    final = pv.iloc[-1]
    ret = (final / cash_start - 1) * 100
    peak = pv.cummax()
    dd = ((pv - peak) / peak).min() * 100
    daily_ret = pv.pct_change().dropna()
    sharpe = daily_ret.mean() / daily_ret.std() * np.sqrt(252) if daily_ret.std() > 0 else 0
    years = len(pv) / 252
    cagr = ((final / cash_start) ** (1/years) - 1) * 100 if years > 0 else 0
    return {
        "final_value": round(final, 2),
        "return_pct": round(ret, 1),
        "max_dd_pct": round(dd, 1),
        "sharpe": round(sharpe, 3),
        "cagr_pct": round(cagr, 1),
    }

# ══════════════════════════════════════
# STRATEGY 1: Dual Momentum Rotation
# - 매월 리밸런싱
# - 12개월 모멘텀 > 0 (절대 모멘텀) AND 최고 모멘텀 종목 선택 (상대 모멘텀)
# - 실패 시 현금
# ══════════════════════════════════════
def strat_dual_momentum(df_dict, assets, lookback=252, rebal_freq=21):
    """assets: list of symbols to rotate between"""
    # Align all to common dates
    common = None
    for sym in assets:
        if sym not in df_dict or df_dict[sym] is None:
            return None
        idx = df_dict[sym].index
        common = idx if common is None else common.intersection(idx)
    common = common.sort_values()

    cash = TOTAL_CASH
    shares = 0.0
    holding = None  # current symbol
    n_trades = 0
    portfolio = []

    for i, date in enumerate(common):
        if i >= lookback and i % rebal_freq == 0:
            # Calculate momentum for each asset
            best_sym = None
            best_mom = -np.inf
            for sym in assets:
                price_now = df_dict[sym].loc[date, "close"]
                past_idx = max(0, i - lookback)
                price_past = df_dict[sym].loc[common[past_idx], "close"]
                mom = (price_now / price_past - 1)
                if mom > 0 and mom > best_mom:
                    best_mom = mom
                    best_sym = sym

            # Switch if needed
            if best_sym != holding:
                if holding is not None and shares > 0:
                    # Sell current
                    cash = shares * df_dict[holding].loc[date, "close"] * (1 - FEE_RATE)
                    shares = 0
                    n_trades += 1
                if best_sym is not None:
                    # Buy new
                    shares = cash * (1 - FEE_RATE) / df_dict[best_sym].loc[date, "close"]
                    cash = 0
                    n_trades += 1
                holding = best_sym

        # Portfolio value
        if holding and shares > 0:
            val = shares * df_dict[holding].loc[date, "close"]
        else:
            val = cash
        portfolio.append(val)

    pv = pd.Series(portfolio, index=common)
    metrics = compute_metrics(pv)
    metrics["n_trades"] = n_trades
    return metrics


# ══════════════════════════════════════
# STRATEGY 2: Volatility Targeting
# - 목표 변동성에 맞춰 포지션 크기 조절
# - 변동성 낮으면 레버리지 풀, 높으면 줄임
# ══════════════════════════════════════
def strat_vol_target(df, target_vol=0.30, rebal_freq=21, max_leverage=1.0):
    close = df["close"].values
    vol = df["vol20"].values
    n = len(df)

    cash = TOTAL_CASH
    shares = 0.0
    n_trades = 0
    portfolio = []

    for i in range(n):
        if i >= 252 and i % rebal_freq == 0 and not np.isnan(vol[i]) and vol[i] > 0:
            # Target weight
            weight = min(target_vol / vol[i], max_leverage)
            target_value = (cash + shares * close[i]) * weight
            current_value = shares * close[i]
            diff = target_value - current_value

            if abs(diff) > (cash + shares * close[i]) * 0.05:  # 5% threshold
                if diff > 0 and cash > 0:
                    buy_amount = min(diff, cash)
                    new_shares = buy_amount * (1 - FEE_RATE) / close[i]
                    shares += new_shares
                    cash -= buy_amount
                    n_trades += 1
                elif diff < 0 and shares > 0:
                    sell_shares = min(-diff / close[i], shares)
                    cash += sell_shares * close[i] * (1 - FEE_RATE)
                    shares -= sell_shares
                    n_trades += 1

        portfolio.append(cash + shares * close[i])

    pv = pd.Series(portfolio, index=df.index)
    metrics = compute_metrics(pv)
    metrics["n_trades"] = n_trades
    return metrics


# ══════════════════════════════════════
# STRATEGY 3: SMA Crossover
# - 가격 > SMA(N) → 보유
# - 가격 < SMA(N) → 현금
# ══════════════════════════════════════
def strat_sma_crossover(df, sma_period=200):
    close = df["close"].values
    sma = df[f"sma{sma_period}"].values if f"sma{sma_period}" in df.columns else df["close"].rolling(sma_period).mean().values
    n = len(df)

    cash = TOTAL_CASH
    shares = 0.0
    in_market = False
    n_trades = 0
    portfolio = []

    for i in range(n):
        if np.isnan(sma[i]):
            portfolio.append(cash)
            continue

        if not in_market and close[i] > sma[i]:
            # Buy
            shares = cash * (1 - FEE_RATE) / close[i]
            cash = 0
            in_market = True
            n_trades += 1
        elif in_market and close[i] < sma[i]:
            # Sell
            cash = shares * close[i] * (1 - FEE_RATE)
            shares = 0
            in_market = False
            n_trades += 1

        portfolio.append(cash + shares * close[i])

    pv = pd.Series(portfolio, index=df.index)
    metrics = compute_metrics(pv)
    metrics["n_trades"] = n_trades
    return metrics


# ══════════════════════════════════════
# STRATEGY 4: Leverage Rotation
# - SMA200 위 + 변동성 낮음 → 3x
# - SMA200 위 + 변동성 높음 → 1x
# - SMA200 아래 → 현금
# ══════════════════════════════════════
def strat_leverage_rotation(df_3x, df_1x, vol_threshold=0.35, rebal_freq=21):
    common = df_3x.index.intersection(df_1x.index).sort_values()

    cash = TOTAL_CASH
    shares = 0.0
    holding = None  # "3x", "1x", or None
    n_trades = 0
    portfolio = []

    for i, date in enumerate(common):
        if i >= 252 and i % rebal_freq == 0:
            price_1x = df_1x.loc[date, "close"]
            sma200_1x = df_1x.loc[date, "sma200"]
            vol_1x = df_1x.loc[date, "vol20"]

            if np.isnan(sma200_1x) or np.isnan(vol_1x):
                portfolio.append(cash + (shares * df_3x.loc[date, "close"] if holding == "3x" else shares * df_1x.loc[date, "close"] if holding == "1x" else 0))
                continue

            target = None
            if price_1x > sma200_1x:
                target = "3x" if vol_1x < vol_threshold else "1x"
            else:
                target = None  # cash

            if target != holding:
                # Sell current
                if holding == "3x" and shares > 0:
                    cash = shares * df_3x.loc[date, "close"] * (1 - FEE_RATE)
                    shares = 0
                    n_trades += 1
                elif holding == "1x" and shares > 0:
                    cash = shares * df_1x.loc[date, "close"] * (1 - FEE_RATE)
                    shares = 0
                    n_trades += 1

                # Buy target
                if target == "3x":
                    shares = cash * (1 - FEE_RATE) / df_3x.loc[date, "close"]
                    cash = 0
                    n_trades += 1
                elif target == "1x":
                    shares = cash * (1 - FEE_RATE) / df_1x.loc[date, "close"]
                    cash = 0
                    n_trades += 1

                holding = target

        if holding == "3x" and shares > 0:
            val = shares * df_3x.loc[date, "close"]
        elif holding == "1x" and shares > 0:
            val = shares * df_1x.loc[date, "close"]
        else:
            val = cash
        portfolio.append(val)

    pv = pd.Series(portfolio, index=common)
    metrics = compute_metrics(pv)
    metrics["n_trades"] = n_trades
    return metrics


# ══════════════════════════════════════
# BASELINES
# ══════════════════════════════════════
def baseline_bh(df):
    shares = TOTAL_CASH * (1 - FEE_RATE) / df["close"].iloc[0]
    pv = shares * df["close"]
    metrics = compute_metrics(pv)
    metrics["n_trades"] = 1
    return metrics

def baseline_dca(df):
    months = df.index.to_period("M")
    unique = months.unique()
    monthly = TOTAL_CASH / len(unique)
    cash = TOTAL_CASH
    shares = 0.0
    prev_month = None
    portfolio = []
    for i in range(len(df)):
        if months.values[i] != prev_month:
            prev_month = months.values[i]
            buy = min(monthly, cash)
            if buy > 1:
                shares += buy * (1 - FEE_RATE) / df["close"].iloc[i]
                cash -= buy
        portfolio.append(cash + shares * df["close"].iloc[i])
    pv = pd.Series(portfolio, index=df.index)
    metrics = compute_metrics(pv)
    metrics["n_trades"] = len(unique)
    return metrics


# ══════════════════════════════════════
# RUN
# ══════════════════════════════════════

# Pairs: 3x ETF → 1x ETF
pairs = [
    ("SOXL", "SOXX"),
    ("TQQQ", "QQQ"),
    ("SPXL", "SPY"),
    ("TNA", "IWM"),
]

# Grid for each strategy
sma_periods = [50, 100, 150, 200]
vol_targets = [0.15, 0.20, 0.25, 0.30, 0.40, 0.50]
mom_lookbacks = [126, 189, 252]
rebal_freqs = [5, 10, 21, 42, 63]
vol_thresholds = [0.20, 0.25, 0.30, 0.35, 0.40, 0.50]

print("Loading data...", flush=True)
df_dict = {}
all_symbols = set()
for lev, base in pairs:
    all_symbols.add(lev)
    all_symbols.add(base)
for sym in all_symbols:
    df_dict[sym] = load_symbol(sym)
    if df_dict[sym] is not None:
        print(f"  {sym}: {len(df_dict[sym])} bars ({df_dict[sym].index[0].date()} ~ {df_dict[sym].index[-1].date()})", flush=True)

os.makedirs("results", exist_ok=True)
all_results = []

for lev_sym, base_sym in pairs:
    df_lev = df_dict.get(lev_sym)
    df_base = df_dict.get(base_sym)
    if df_lev is None or df_base is None:
        print(f"SKIP {lev_sym}/{base_sym}: data missing", flush=True)
        continue

    # Common period
    common_start = max(df_lev.index[0], df_base.index[0])
    df_lev_c = df_lev[df_lev.index >= common_start]
    df_base_c = df_base[df_base.index >= common_start]

    print(f"\n{'='*100}", flush=True)
    print(f"{lev_sym}(3x) vs {base_sym}(1x) | {common_start.date()} ~ {df_lev_c.index[-1].date()} | {len(df_lev_c)} bars", flush=True)
    print(f"{'='*100}", flush=True)

    # Baselines
    for sym, df_sym, label in [(lev_sym, df_lev_c, "3x"), (base_sym, df_base_c, "1x")]:
        for strat_name, func in [("B&H", baseline_bh), ("DCA", baseline_dca)]:
            m = func(df_sym)
            m.update({"pair": f"{lev_sym}/{base_sym}", "symbol": sym, "leverage": label,
                      "strategy": strat_name, "params": "-"})
            all_results.append(m)

    # Strategy 1: Dual Momentum (rotate between 3x and 1x)
    for lb in mom_lookbacks:
        for rf in rebal_freqs:
            m = strat_dual_momentum(df_dict, [lev_sym, base_sym], lookback=lb, rebal_freq=rf)
            if m:
                m.update({"pair": f"{lev_sym}/{base_sym}", "symbol": f"{lev_sym}|{base_sym}",
                          "leverage": "rotate", "strategy": "1.DualMom",
                          "params": f"lb={lb},rf={rf}"})
                all_results.append(m)

    # Strategy 2: Volatility Targeting (on 3x)
    for vt in vol_targets:
        for rf in rebal_freqs:
            m = strat_vol_target(df_lev_c, target_vol=vt, rebal_freq=rf)
            m.update({"pair": f"{lev_sym}/{base_sym}", "symbol": lev_sym,
                      "leverage": "3x", "strategy": "2.VolTarget",
                      "params": f"vol={vt},rf={rf}"})
            all_results.append(m)

    # Strategy 2b: Vol Target on 1x
    for vt in vol_targets:
        for rf in rebal_freqs:
            m = strat_vol_target(df_base_c, target_vol=vt, rebal_freq=rf)
            m.update({"pair": f"{lev_sym}/{base_sym}", "symbol": base_sym,
                      "leverage": "1x", "strategy": "2.VolTarget",
                      "params": f"vol={vt},rf={rf}"})
            all_results.append(m)

    # Strategy 3: SMA Crossover (on both)
    for sma_p in sma_periods:
        for sym, df_sym, label in [(lev_sym, df_lev_c, "3x"), (base_sym, df_base_c, "1x")]:
            m = strat_sma_crossover(df_sym, sma_period=sma_p)
            m.update({"pair": f"{lev_sym}/{base_sym}", "symbol": sym,
                      "leverage": label, "strategy": "3.SMA_Cross",
                      "params": f"sma={sma_p}"})
            all_results.append(m)

    # Strategy 4: Leverage Rotation (3x/1x/cash)
    for vth in vol_thresholds:
        for rf in rebal_freqs:
            m = strat_leverage_rotation(df_lev_c, df_base_c, vol_threshold=vth, rebal_freq=rf)
            m.update({"pair": f"{lev_sym}/{base_sym}", "symbol": f"{lev_sym}|{base_sym}",
                      "leverage": "rotate", "strategy": "4.LevRotation",
                      "params": f"vth={vth},rf={rf}"})
            all_results.append(m)

    print(f"  Combos done: {sum(1 for r in all_results if r['pair'] == f'{lev_sym}/{base_sym}')}", flush=True)

# Save CSV
res_df = pd.DataFrame(all_results)
cols = ["pair", "symbol", "leverage", "strategy", "params", "n_trades",
        "final_value", "return_pct", "cagr_pct", "max_dd_pct", "sharpe"]
res_df = res_df[cols]
res_df.to_csv("results/full_strategy_comparison.csv", index=False)
print(f"\nSaved: results/full_strategy_comparison.csv ({len(res_df)} rows)", flush=True)

# ── Print summary per pair ──
for lev_sym, base_sym in pairs:
    pair = f"{lev_sym}/{base_sym}"
    sub = res_df[res_df["pair"] == pair].copy()
    if len(sub) == 0:
        continue

    sub = sub.sort_values("return_pct", ascending=False)
    bh_3x = sub[(sub["strategy"] == "B&H") & (sub["leverage"] == "3x")]["return_pct"].values
    bh_3x = bh_3x[0] if len(bh_3x) > 0 else 0
    bh_1x = sub[(sub["strategy"] == "B&H") & (sub["leverage"] == "1x")]["return_pct"].values
    bh_1x = bh_1x[0] if len(bh_1x) > 0 else 0

    print(f"\n{'='*120}")
    print(f"{pair} | B&H 3x: {bh_3x:,.1f}% | B&H 1x: {bh_1x:,.1f}%")
    print(f"{'='*120}")
    print(f"{'#':<3} {'Trades':>6} {'Strategy':<16} {'Lev':<7} {'Params':<20} {'Return%':>10} {'CAGR%':>7} {'MaxDD%':>7} {'Sharpe':>7} {'vs3xBH':>10}")
    print("-"*120)

    for i, (_, r) in enumerate(sub.head(30).iterrows()):
        vs = r["return_pct"] - bh_3x
        print(f"{i:<3} {r['n_trades']:>6} {r['strategy']:<16} {r['leverage']:<7} {r['params']:<20} "
              f"{r['return_pct']:>9,.1f}% {r['cagr_pct']:>6.1f}% {r['max_dd_pct']:>6.1f}% {r['sharpe']:>7.3f} {vs:>+9,.1f}%")

    # Best per strategy
    print(f"\n  BEST PER STRATEGY:")
    for strat in ["B&H", "DCA", "1.DualMom", "2.VolTarget", "3.SMA_Cross", "4.LevRotation"]:
        s = sub[sub["strategy"] == strat]
        if len(s) == 0:
            continue
        best = s.iloc[0]
        print(f"    {strat:<16} {best['leverage']:<7} {best['params']:<20} "
              f"ret={best['return_pct']:>9,.1f}%  CAGR={best['cagr_pct']:>5.1f}%  "
              f"MaxDD={best['max_dd_pct']:>6.1f}%  Sharpe={best['sharpe']:.3f}  "
              f"trades={best['n_trades']}")
