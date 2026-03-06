"""
실험 2: ATR 기반 포지션 사이징
- RSI 시그널은 동일, 진입 시 포지션 크기를 ATR(평균진폭)에 반비례
- 변동성 높으면 적게, 낮으면 많이 → 리스크 균등화
"""
import pandas as pd
import numpy as np
import os, time

TOTAL_CASH = 10000.0
FEE_RATE = 0.0025

SYMBOLS = ["SOXL", "TQQQ", "SPXL", "TNA", "QLD", "UWM", "QQQ"]
PARAMS = {
    "SOXL": (25, 60, 55), "TQQQ": (25, 65, 55), "SPXL": (30, 70, 55),
    "TNA": (35, 70, 50), "QLD": (25, 70, 55), "UWM": (25, 70, 50), "QQQ": (25, 75, 55),
}


def rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def atr(high, low, close, period=14):
    tr = np.maximum(high - low, np.maximum(abs(high - close.shift(1)), abs(low - close.shift(1))))
    return tr.rolling(period).mean()


def bollinger_upper(series, period=20, num_std=2):
    sma = series.rolling(period).mean()
    std = series.rolling(period).std()
    return sma + num_std * std


def run_atr_sized(close, high, low, rsi_arr, bb_upper, atr_arr,
                  buy_rsi, sell_rsi, rebuy_rsi, risk_pct, atr_mult):
    """
    risk_pct: 1회 매매당 리스크 비율 (e.g. 0.02 = 2%)
    atr_mult: ATR 배수 (스탑 거리)
    position_size = (cash * risk_pct) / (ATR * atr_mult)
    → ATR 높으면 포지션 작아짐
    """
    n = len(close)
    cash = TOTAL_CASH
    shares = 0.0
    state = 0
    n_buys = 0; n_sells = 0
    peak_val = TOTAL_CASH; max_dd = 0.0

    for i in range(n):
        price = close[i]
        rv = rsi_arr[i]
        bb = bb_upper[i]
        av = atr_arr[i]

        if np.isnan(rv) or np.isnan(bb) or np.isnan(av) or av <= 0:
            val = cash + shares * price
            if val > peak_val: peak_val = val
            continue

        if state == 0:
            if rv < buy_rsi:
                # ATR-based position sizing
                risk_per_share = av * atr_mult
                max_shares = (cash * risk_pct) / risk_per_share
                buy_value = min(max_shares * price, cash)
                if buy_value > 1:
                    shares = buy_value * (1 - FEE_RATE) / price
                    cash -= buy_value
                    n_buys += 1; state = 1

        elif state == 1:
            if rv > sell_rsi and price > bb:
                cash += shares * price * (1 - FEE_RATE)
                shares = 0; n_sells += 1; state = 2

        elif state == 2:
            if rv < rebuy_rsi:
                risk_per_share = av * atr_mult
                max_shares = (cash * risk_pct) / risk_per_share
                buy_value = min(max_shares * price, cash)
                if buy_value > 1:
                    shares = buy_value * (1 - FEE_RATE) / price
                    cash -= buy_value
                    n_buys += 1; state = 1

        val = cash + shares * price
        if val > peak_val: peak_val = val
        dd = (val - peak_val) / peak_val
        if dd < max_dd: max_dd = dd

    final = cash + shares * close[-1]
    ret = (final / TOTAL_CASH - 1) * 100
    return n_buys, n_sells, round(ret, 1), round(max_dd * 100, 1)


def run_baseline(close, rsi_arr, bb_upper, buy_rsi, sell_rsi, rebuy_rsi):
    """올인/올아웃 baseline"""
    n = len(close)
    cash = TOTAL_CASH; shares = 0.0; state = 0
    n_buys = 0; n_sells = 0; peak_val = TOTAL_CASH; max_dd = 0.0

    for i in range(n):
        price = close[i]; rv = rsi_arr[i]; bb = bb_upper[i]
        if np.isnan(rv) or np.isnan(bb):
            val = cash + shares * price
            if val > peak_val: peak_val = val
            continue
        if state == 0 and rv < buy_rsi:
            shares = cash * (1 - FEE_RATE) / price; cash = 0; n_buys += 1; state = 1
        elif state == 1 and rv > sell_rsi and price > bb:
            cash = shares * price * (1 - FEE_RATE); shares = 0; n_sells += 1; state = 2
        elif state == 2 and rv < rebuy_rsi:
            shares = cash * (1 - FEE_RATE) / price; cash = 0; n_buys += 1; state = 1
        val = cash + shares * price
        if val > peak_val: peak_val = val
        dd = (val - peak_val) / peak_val
        if dd < max_dd: max_dd = dd

    final = cash + shares * close[-1]
    return n_buys, n_sells, round((final / TOTAL_CASH - 1) * 100, 1), round(max_dd * 100, 1)


def run_bh(close):
    shares = TOTAL_CASH * (1 - FEE_RATE) / close[0]
    return round((shares * close[-1] / TOTAL_CASH - 1) * 100, 1)


def main():
    print("=" * 120)
    print("EXP 2: ATR-BASED POSITION SIZING")
    print("=" * 120)

    risk_pcts = [0.01, 0.02, 0.05, 0.10, 0.20, 0.50, 1.0]
    atr_mults = [1.0, 1.5, 2.0, 3.0]
    all_results = []

    for sym in SYMBOLS:
        if not os.path.exists(f"data/{sym}.parquet"):
            continue
        df = pd.read_parquet(f"data/{sym}.parquet").sort_index()
        df["rsi14"] = rsi(df["close"], 14)
        df["atr14"] = atr(df["high"], df["low"], df["close"], 14)
        df["bb_upper"] = bollinger_upper(df["close"], 20, 2)

        close = df["close"].values
        high = df["high"].values
        low = df["low"].values
        rsi_arr = df["rsi14"].values
        atr_arr = df["atr14"].values
        bb_arr = df["bb_upper"].values
        buy_r, sell_r, rebuy_r = PARAMS[sym]

        bh = run_bh(close)
        nb0, ns0, base_ret, base_dd = run_baseline(close, rsi_arr, bb_arr, buy_r, sell_r, rebuy_r)

        print(f"\n[{sym}] {len(df)} bars | B&H: {bh:>+10,.1f}% | RSI(all-in): {base_ret:>+10,.1f}% ({nb0}B/{ns0}S, MaxDD {base_dd}%)")

        best_ret = -999; best_row = None
        best_dd_improvement = 0; best_dd_row = None

        for rp in risk_pcts:
            for am in atr_mults:
                nb, ns, ret, mdd = run_atr_sized(close, high, low, rsi_arr, bb_arr, atr_arr,
                                                  buy_r, sell_r, rebuy_r, rp, am)
                row = {
                    "symbol": sym, "risk_pct": rp, "atr_mult": am,
                    "n_buys": nb, "n_sells": ns, "return_pct": ret, "max_dd_pct": mdd,
                    "bh_pct": bh, "baseline_pct": base_ret, "baseline_dd": base_dd,
                    "vs_bh": round(ret - bh, 1), "vs_baseline": round(ret - base_ret, 1),
                    "dd_improvement": round(base_dd - mdd, 1),
                }
                all_results.append(row)
                if ret > best_ret:
                    best_ret = ret; best_row = row
                if mdd > base_dd and ret > base_ret * 0.5:
                    dd_imp = base_dd - mdd
                    if dd_imp > best_dd_improvement:
                        best_dd_improvement = dd_imp; best_dd_row = row

        print(f"  Best return: {best_ret:>+10,.1f}% | risk={best_row['risk_pct']} atr_mult={best_row['atr_mult']} "
              f"({best_row['n_buys']}B/{best_row['n_sells']}S, MaxDD {best_row['max_dd_pct']}%)")
        if best_dd_row:
            print(f"  Best MaxDD:  {best_dd_row['return_pct']:>+10,.1f}% | MaxDD {best_dd_row['max_dd_pct']}% "
                  f"(improvement {best_dd_improvement:+.1f}%p) risk={best_dd_row['risk_pct']} atr={best_dd_row['atr_mult']}")

    res_df = pd.DataFrame(all_results)
    res_df.to_csv("results/exp2_atr_sizing.csv", index=False)

    print(f"\n{'='*100}")
    print("SUMMARY: ATR sizing vs All-in (best per symbol)")
    print(f"{'='*100}")
    print(f"{'Sym':<6} {'All-in%':>10} {'All-in DD':>10} {'ATR best%':>10} {'ATR DD':>8} {'vs All-in':>10} {'DD improv':>10} {'Risk':>6} {'ATR_m':>6} {'B/S':>8}")
    for sym in SYMBOLS:
        sub = res_df[res_df["symbol"] == sym]
        if sub.empty: continue
        best = sub.loc[sub["return_pct"].idxmax()]
        print(f"{sym:<6} {best['baseline_pct']:>+9,.1f}% {best['baseline_dd']:>9.1f}% "
              f"{best['return_pct']:>+9,.1f}% {best['max_dd_pct']:>7.1f}% "
              f"{best['vs_baseline']:>+9,.1f}% {best['dd_improvement']:>+9.1f}%p "
              f"{best['risk_pct']:>5} {best['atr_mult']:>5} {best['n_buys']}B/{best['n_sells']}S")

    print(f"\nSaved: results/exp2_atr_sizing.csv")


if __name__ == "__main__":
    main()
