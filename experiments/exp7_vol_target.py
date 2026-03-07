"""
실험 7: Volatility Targeting
- 목표 변동성에 맞춰 포지션 크기 동적 조절
- RSI 시그널 + 변동성 타겟 포지션 사이징
- 비교: 올인 vs vol-target
"""
import pandas as pd
import numpy as np
import os

TOTAL_CASH = 10000.0
FEE_RATE = 0.0025

SYMBOLS = ["SOXL", "TQQQ", "SPXL", "TNA"]
TARGET_VOLS = [0.10, 0.15, 0.20, 0.25, 0.30]
VOL_WINDOWS = [21, 42, 63]

RSI_PARAMS = {
    "SOXL": (25, 60, 55), "TQQQ": (25, 65, 55),
    "SPXL": (30, 70, 55), "TNA": (35, 70, 50),
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


def run_vol_target(close, rsi_arr, bb_arr, vol_arr, target_vol,
                   buy_rsi, sell_rsi, rebuy_rsi):
    n = len(close)
    cash = TOTAL_CASH
    shares = 0.0
    state = 0
    n_buys = 0; n_sells = 0
    peak_val = TOTAL_CASH; max_dd = 0.0

    for i in range(n):
        price = close[i]
        rv = rsi_arr[i]
        bb = bb_arr[i]
        v = vol_arr[i]

        if np.isnan(rv) or np.isnan(bb) or np.isnan(v) or v <= 0:
            val = cash + shares * price
            if val > peak_val: peak_val = val
            continue

        position_pct = min(target_vol / v, 1.0)
        total_val = cash + shares * price

        if state == 0:
            if rv < buy_rsi:
                invest = min(total_val * position_pct, cash)
                if invest > 1:
                    shares = invest * (1 - FEE_RATE) / price
                    cash -= invest
                    n_buys += 1; state = 1
        elif state == 1:
            if rv > sell_rsi and price > bb:
                cash += shares * price * (1 - FEE_RATE)
                shares = 0; n_sells += 1; state = 2
            else:
                # Rebalance position size based on current vol
                target_val = total_val * position_pct
                current_pos_val = shares * price
                diff_pct = (target_val - current_pos_val) / max(total_val, 1)
                if abs(diff_pct) > 0.10:  # >10% drift
                    if target_val > current_pos_val and cash > 0:
                        buy_amt = min(target_val - current_pos_val, cash)
                        shares += buy_amt * (1 - FEE_RATE) / price
                        cash -= buy_amt
                    elif target_val < current_pos_val and shares > 0:
                        sell_shares = (current_pos_val - target_val) / price
                        sell_shares = min(sell_shares, shares)
                        cash += sell_shares * price * (1 - FEE_RATE)
                        shares -= sell_shares
        elif state == 2:
            if rv < rebuy_rsi:
                invest = min(total_val * position_pct, cash)
                if invest > 1:
                    shares = invest * (1 - FEE_RATE) / price
                    cash -= invest
                    n_buys += 1; state = 1

        val = cash + shares * price
        if val > peak_val: peak_val = val
        dd = (val - peak_val) / peak_val
        if dd < max_dd: max_dd = dd

    final = cash + shares * close[-1]
    ret = (final / TOTAL_CASH - 1) * 100
    return n_buys, n_sells, round(ret, 1), round(max_dd * 100, 1)


def run_allin(close, rsi_arr, bb_arr, buy_rsi, sell_rsi, rebuy_rsi):
    n = len(close)
    cash = TOTAL_CASH
    shares = 0.0
    state = 0
    n_buys = 0; n_sells = 0
    peak_val = TOTAL_CASH; max_dd = 0.0

    for i in range(n):
        price = close[i]
        rv = rsi_arr[i]
        bb = bb_arr[i]
        if np.isnan(rv) or np.isnan(bb):
            val = cash + shares * price
            if val > peak_val: peak_val = val
            continue

        if state == 0:
            if rv < buy_rsi:
                shares = cash * (1 - FEE_RATE) / price
                cash = 0; n_buys += 1; state = 1
        elif state == 1:
            if rv > sell_rsi and price > bb:
                cash = shares * price * (1 - FEE_RATE)
                shares = 0; n_sells += 1; state = 2
        elif state == 2:
            if rv < rebuy_rsi:
                shares = cash * (1 - FEE_RATE) / price
                cash = 0; n_buys += 1; state = 1

        val = cash + shares * price
        if val > peak_val: peak_val = val
        dd = (val - peak_val) / peak_val
        if dd < max_dd: max_dd = dd

    final = cash + shares * close[-1]
    ret = (final / TOTAL_CASH - 1) * 100
    return n_buys, n_sells, round(ret, 1), round(max_dd * 100, 1)


def run_bh(close):
    shares = TOTAL_CASH * (1 - FEE_RATE) / close[0]
    return round((shares * close[-1] / TOTAL_CASH - 1) * 100, 1)


def main():
    print("=" * 120)
    print("EXP 7: VOLATILITY TARGETING")
    print("=" * 120)

    all_results = []

    for sym in SYMBOLS:
        path = f"data/{sym}.parquet"
        if not os.path.exists(path):
            print(f"  SKIP {sym}: data not found")
            continue

        df = pd.read_parquet(path).sort_index()
        close = df["close"].values
        rsi_arr = rsi(df["close"], 14).values
        bb_arr = bollinger_upper(df["close"], 20, 2).values

        buy_r, sell_r, rebuy_r = RSI_PARAMS[sym]
        bh_ret = run_bh(close)

        ab, as_, aret, add = run_allin(close, rsi_arr, bb_arr, buy_r, sell_r, rebuy_r)

        print(f"\n[{sym}] {len(close)} bars | B&H: {bh_ret:+.1f}%")
        print(f"  All-in:  {aret:>+10,.1f}% ({ab}B/{as_}S, MaxDD {add}%)")

        best_ret = -999; best_row = None
        best_dd_row = None; best_dd_improve = 999

        for vw in VOL_WINDOWS:
            log_ret = np.log(df["close"] / df["close"].shift(1))
            vol_s = log_ret.rolling(vw).std() * np.sqrt(252)
            vol_arr = vol_s.values

            for tv in TARGET_VOLS:
                nb, ns, ret, mdd = run_vol_target(
                    close, rsi_arr, bb_arr, vol_arr, tv,
                    buy_r, sell_r, rebuy_r)

                row = {
                    "symbol": sym, "vol_window": vw, "target_vol": tv,
                    "n_buys": nb, "n_sells": ns,
                    "return_pct": ret, "max_dd_pct": mdd,
                    "allin_pct": aret, "allin_dd": add,
                    "bh_pct": bh_ret,
                    "vs_allin": round(ret - aret, 1),
                    "vs_bh": round(ret - bh_ret, 1),
                    "dd_improvement": round(mdd - add, 1),
                }
                all_results.append(row)

                if ret > best_ret:
                    best_ret = ret; best_row = row
                if mdd > best_dd_improve:  # less negative = better
                    best_dd_improve = mdd; best_dd_row = row

        if best_row:
            print(f"  Best VT: {best_ret:>+10,.1f}% | vw={best_row['vol_window']} "
                  f"target={best_row['target_vol']} ({best_row['n_buys']}B/{best_row['n_sells']}S, "
                  f"MaxDD {best_row['max_dd_pct']}%)")
            print(f"  vs All-in: {best_row['vs_allin']:+.1f}% | DD change: {best_row['dd_improvement']:+.1f}%")

    res_df = pd.DataFrame(all_results)
    res_df.to_csv("results/exp7_vol_target.csv", index=False)
    print(f"\nSaved: results/exp7_vol_target.csv ({len(all_results)} rows)")


if __name__ == "__main__":
    main()
