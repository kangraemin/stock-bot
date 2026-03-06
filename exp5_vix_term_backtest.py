"""
실험 5: VIX Term Structure 기반 매매
- VIX vs VIX3M (3개월 VIX) 비교
- Contango (VIX < VIX3M): 정상 시장 → risk-on
- Backwardation (VIX > VIX3M): 공포 시장 → risk-off
- VIX/VIX3M ratio를 시그널로 사용
"""
import pandas as pd
import numpy as np
import os, time
import yfinance as yf

TOTAL_CASH = 10000.0
FEE_RATE = 0.0025

SYMBOLS = ["SOXL", "TQQQ", "SPXL", "TNA"]
PARAMS = {
    "SOXL": (25, 60, 55), "TQQQ": (25, 65, 55), "SPXL": (30, 70, 55), "TNA": (35, 70, 50),
}


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


def download_vix_data():
    """VIX + VIX3M 다운로드"""
    vix_path = "data/^VIX.parquet"
    vix3m_path = "data/^VIX3M.parquet"

    if not os.path.exists(vix3m_path):
        print("  Downloading VIX3M...")
        df = yf.download("^VIX3M", period="max", progress=False, auto_adjust=True)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df.columns = [c.lower() for c in df.columns]
        df.to_parquet(vix3m_path)

    vix = pd.read_parquet(vix_path).sort_index()
    vix3m = pd.read_parquet(vix3m_path).sort_index()
    return vix, vix3m


def run_vix_term_filter(close, rsi_arr, bb_upper, vix_ratio,
                         buy_rsi, sell_rsi, rebuy_rsi,
                         mode, ratio_thresh):
    """
    mode:
      "block": backwardation(ratio > ratio_thresh)에서 매수 차단
      "force": backwardation에서 강제 매도
      "block+force": 둘 다
      "adjust": contango에서 RSI +5, backwardation에서 RSI -5
      "ratio_scale": ratio에 비례해서 포지션 사이즈 조절
    """
    n = len(close)
    cash = TOTAL_CASH; shares = 0.0; state = 0
    n_buys = 0; n_sells = 0
    peak_val = TOTAL_CASH; max_dd = 0.0

    for i in range(n):
        price = close[i]; rv = rsi_arr[i]; bb = bb_upper[i]; vr = vix_ratio[i]
        if np.isnan(rv) or np.isnan(bb) or np.isnan(vr):
            val = cash + shares * price
            if val > peak_val: peak_val = val
            continue

        is_backwardation = vr > ratio_thresh
        is_contango = vr < (1.0 / ratio_thresh)

        if mode == "adjust":
            if is_contango:
                adj_buy, adj_sell, adj_rebuy = buy_rsi + 5, sell_rsi + 5, rebuy_rsi + 5
            elif is_backwardation:
                adj_buy, adj_sell, adj_rebuy = buy_rsi - 5, sell_rsi - 5, rebuy_rsi - 5
            else:
                adj_buy, adj_sell, adj_rebuy = buy_rsi, sell_rsi, rebuy_rsi
            adj_buy = max(10, min(adj_buy, 50))
            adj_sell = max(50, min(adj_sell, 90))
            adj_rebuy = max(15, min(adj_rebuy, 65))
        else:
            adj_buy, adj_sell, adj_rebuy = buy_rsi, sell_rsi, rebuy_rsi

        # Force sell in backwardation
        if mode in ("force", "block+force") and is_backwardation and state == 1:
            cash = shares * price * (1 - FEE_RATE)
            shares = 0; n_sells += 1; state = 2

        if state == 0:
            if rv < adj_buy:
                blocked = mode in ("block", "block+force") and is_backwardation
                if not blocked:
                    if mode == "ratio_scale":
                        # Scale: contango → full, backwardation → smaller
                        scale = max(0.2, min(1.0, 1.0 / vr)) if vr > 0 else 1.0
                        buy_amt = cash * scale
                    else:
                        buy_amt = cash
                    if buy_amt > 1:
                        shares = buy_amt * (1 - FEE_RATE) / price
                        cash -= buy_amt
                        n_buys += 1; state = 1

        elif state == 1:
            if rv > adj_sell and price > bb:
                cash += shares * price * (1 - FEE_RATE)
                shares = 0; n_sells += 1; state = 2

        elif state == 2:
            if rv < adj_rebuy:
                blocked = mode in ("block", "block+force") and is_backwardation
                if not blocked:
                    if mode == "ratio_scale":
                        scale = max(0.2, min(1.0, 1.0 / vr)) if vr > 0 else 1.0
                        buy_amt = cash * scale
                    else:
                        buy_amt = cash
                    if buy_amt > 1:
                        shares = buy_amt * (1 - FEE_RATE) / price
                        cash -= buy_amt
                        n_buys += 1; state = 1

        val = cash + shares * price
        if val > peak_val: peak_val = val
        dd = (val - peak_val) / peak_val
        if dd < max_dd: max_dd = dd

    final = cash + shares * close[-1]
    ret = (final / TOTAL_CASH - 1) * 100
    return n_buys, n_sells, round(ret, 1), round(max_dd * 100, 1)


def run_baseline(close, rsi_arr, bb_upper, buy_rsi, sell_rsi, rebuy_rsi):
    n = len(close); cash = TOTAL_CASH; shares = 0.0; state = 0
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
    print("EXP 5: VIX TERM STRUCTURE (Contango/Backwardation)")
    print("=" * 120)

    vix_df, vix3m_df = download_vix_data()
    print(f"VIX: {len(vix_df)} bars | VIX3M: {len(vix3m_df)} bars")

    modes = ["block", "force", "block+force", "adjust", "ratio_scale"]
    ratio_thresholds = [1.0, 1.05, 1.10, 1.15, 1.20]
    all_results = []

    for sym in SYMBOLS:
        if not os.path.exists(f"data/{sym}.parquet"):
            continue

        df = pd.read_parquet(f"data/{sym}.parquet").sort_index()
        df["rsi14"] = rsi(df["close"], 14)
        df["bb_upper"] = bollinger_upper(df["close"], 20, 2)

        common = df.index.intersection(vix_df.index).intersection(vix3m_df.index).sort_values()
        close = df.loc[common, "close"].values
        rsi_arr = df.loc[common, "rsi14"].values
        bb_arr = df.loc[common, "bb_upper"].values
        vix_ratio = (vix_df.loc[common, "close"] / vix3m_df.loc[common, "close"]).values

        bh = run_bh(close)
        buy_r, sell_r, rebuy_r = PARAMS[sym]
        nb0, ns0, base_ret, base_dd = run_baseline(close, rsi_arr, bb_arr, buy_r, sell_r, rebuy_r)

        print(f"\n[{sym}] {len(common)} bars | B&H: {bh:>+10,.1f}% | RSI: {base_ret:>+10,.1f}% ({nb0}B/{ns0}S)")

        # Stats on VIX ratio
        vr_valid = vix_ratio[~np.isnan(vix_ratio)]
        pct_backwardation = (vr_valid > 1.0).sum() / len(vr_valid) * 100
        print(f"  VIX/VIX3M: mean={np.nanmean(vix_ratio):.3f} | backwardation {pct_backwardation:.0f}% of days")

        best_ret = -999; best_row = None
        for mode in modes:
            for rt in ratio_thresholds:
                nb, ns, ret, mdd = run_vix_term_filter(
                    close, rsi_arr, bb_arr, vix_ratio,
                    buy_r, sell_r, rebuy_r, mode, rt)
                row = {
                    "symbol": sym, "mode": mode, "ratio_thresh": rt,
                    "n_buys": nb, "n_sells": ns, "return_pct": ret, "max_dd_pct": mdd,
                    "bh_pct": bh, "rsi_pct": base_ret,
                    "vs_bh": round(ret - bh, 1), "vs_rsi": round(ret - base_ret, 1),
                }
                all_results.append(row)
                if ret > best_ret:
                    best_ret = ret; best_row = row

        print(f"  Best: {best_ret:>+10,.1f}% | {best_row['mode']} ratio>{best_row['ratio_thresh']} "
              f"({best_row['n_buys']}B/{best_row['n_sells']}S, MaxDD {best_row['max_dd_pct']}%) "
              f"vs RSI: {best_row['vs_rsi']:+.1f}%")

    res_df = pd.DataFrame(all_results)
    res_df.to_csv("results/exp5_vix_term.csv", index=False)

    # Summary
    print(f"\n{'='*100}")
    print("SUMMARY: VIX Term Structure vs RSI baseline")
    print(f"{'='*100}")
    for sym in SYMBOLS:
        sub = res_df[res_df["symbol"] == sym]
        if sub.empty: continue
        best = sub.loc[sub["return_pct"].idxmax()]
        beat_rsi = len(sub[sub["vs_rsi"] > 0])
        print(f"  {sym}: best {best['mode']:<13} ratio>{best['ratio_thresh']:.2f} → "
              f"{best['return_pct']:>+10,.1f}% vs RSI {best['vs_rsi']:>+8,.1f}% "
              f"({best['n_buys']}B/{best['n_sells']}S) | beat RSI: {beat_rsi}/{len(sub)}")

    print(f"\nSaved: results/exp5_vix_term.csv")


if __name__ == "__main__":
    main()
