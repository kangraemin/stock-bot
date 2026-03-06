"""
실험 3: 변동성 기반 레버리지 스위칭
- 변동성 낮으면 3x, 보통이면 2x, 높으면 1x or 현금
- 실현 변동성(realized vol) + VIX 기반 레짐
"""
import pandas as pd
import numpy as np
import os, time

TOTAL_CASH = 10000.0
FEE_RATE = 0.0025

# (3x, 2x, 1x) 심볼
TRIOS = [
    ("SOXL", "USD", "SOXX"),   # USD는 2x semi 없어서 SOXX로 대체
    ("TQQQ", "QLD", "QQQ"),
    ("SPXL", "SSO", "SPY"),
    ("TNA", "UWM", "IWM"),
]


def realized_vol(close, window=20):
    """연율화된 실현 변동성"""
    log_ret = np.log(close / close.shift(1))
    return log_ret.rolling(window).std() * np.sqrt(252)


def run_lev_switch(close_3x, close_2x, close_1x, vol_arr, vix_arr,
                   vol_low, vol_high, vix_threshold, use_vix):
    """
    vol < vol_low → 3x
    vol_low <= vol < vol_high → 2x
    vol >= vol_high → 1x
    vix > vix_threshold → cash (if use_vix)
    """
    n = len(close_3x)
    cash = TOTAL_CASH
    shares = 0.0
    current_lev = None  # "3x", "2x", "1x", "cash"
    n_switches = 0
    peak_val = TOTAL_CASH; max_dd = 0.0

    for i in range(n):
        v = vol_arr[i]
        vx = vix_arr[i] if vix_arr is not None else 0

        if np.isnan(v):
            val = cash + shares * (close_3x[i] if current_lev == "3x" else
                                   close_2x[i] if current_lev == "2x" else
                                   close_1x[i] if current_lev == "1x" else 0)
            if val > peak_val: peak_val = val
            continue

        # Determine target
        if use_vix and not np.isnan(vx) and vx > vix_threshold:
            target = "cash"
        elif v < vol_low:
            target = "3x"
        elif v < vol_high:
            target = "2x"
        else:
            target = "1x"

        if target != current_lev:
            # Liquidate
            if current_lev == "3x":
                cash += shares * close_3x[i] * (1 - FEE_RATE)
            elif current_lev == "2x":
                cash += shares * close_2x[i] * (1 - FEE_RATE)
            elif current_lev == "1x":
                cash += shares * close_1x[i] * (1 - FEE_RATE)
            shares = 0

            # Buy new
            if target == "3x" and cash > 1:
                shares = cash * (1 - FEE_RATE) / close_3x[i]; cash = 0
            elif target == "2x" and cash > 1:
                shares = cash * (1 - FEE_RATE) / close_2x[i]; cash = 0
            elif target == "1x" and cash > 1:
                shares = cash * (1 - FEE_RATE) / close_1x[i]; cash = 0

            if current_lev is not None:
                n_switches += 1
            current_lev = target

        # Portfolio value
        if current_lev == "3x":
            val = cash + shares * close_3x[i]
        elif current_lev == "2x":
            val = cash + shares * close_2x[i]
        elif current_lev == "1x":
            val = cash + shares * close_1x[i]
        else:
            val = cash

        if val > peak_val: peak_val = val
        dd = (val - peak_val) / peak_val
        if dd < max_dd: max_dd = dd

    # Final value
    if current_lev == "3x":
        final = cash + shares * close_3x[-1]
    elif current_lev == "2x":
        final = cash + shares * close_2x[-1]
    elif current_lev == "1x":
        final = cash + shares * close_1x[-1]
    else:
        final = cash

    ret = (final / TOTAL_CASH - 1) * 100
    return n_switches, round(ret, 1), round(max_dd * 100, 1)


def run_bh(close):
    shares = TOTAL_CASH * (1 - FEE_RATE) / close[0]
    return round((shares * close[-1] / TOTAL_CASH - 1) * 100, 1)


def main():
    print("=" * 120)
    print("EXP 3: VOLATILITY-BASED LEVERAGE SWITCHING")
    print("=" * 120)

    # Load VIX
    vix_df = None
    if os.path.exists("data/^VIX.parquet"):
        vix_df = pd.read_parquet("data/^VIX.parquet").sort_index()

    vol_lows = [0.15, 0.20, 0.25, 0.30]
    vol_highs = [0.30, 0.35, 0.40, 0.50, 0.60]
    vix_thresholds = [25, 30, 35, 999]  # 999 = no VIX filter
    vol_windows = [20, 50]

    all_results = []

    for sym_3x, sym_2x, sym_1x in TRIOS:
        avail = all(os.path.exists(f"data/{s}.parquet") for s in [sym_3x, sym_2x, sym_1x])
        if not avail:
            # Try without 2x
            if not os.path.exists(f"data/{sym_3x}.parquet") or not os.path.exists(f"data/{sym_1x}.parquet"):
                print(f"  SKIP {sym_3x}: data not found")
                continue
            # Use 1x as 2x substitute
            sym_2x = sym_1x

        df_3x = pd.read_parquet(f"data/{sym_3x}.parquet").sort_index()
        df_2x = pd.read_parquet(f"data/{sym_2x}.parquet").sort_index()
        df_1x = pd.read_parquet(f"data/{sym_1x}.parquet").sort_index()

        common = df_3x.index.intersection(df_2x.index).intersection(df_1x.index)
        if vix_df is not None:
            common = common.intersection(vix_df.index)
        common = common.sort_values()

        close_3x = df_3x.loc[common, "close"].values
        close_2x = df_2x.loc[common, "close"].values
        close_1x = df_1x.loc[common, "close"].values
        vix_arr = vix_df.loc[common, "close"].values if vix_df is not None else None

        bh_3x = run_bh(close_3x)
        bh_1x = run_bh(close_1x)

        print(f"\n[{sym_3x}/{sym_2x}/{sym_1x}] {len(common)} bars")
        print(f"  B&H 3x: {bh_3x:>+10,.1f}% | B&H 1x: {bh_1x:>+10,.1f}%")

        best_ret = -999; best_row = None
        best_risk_adj = -999; best_ra_row = None

        for vw in vol_windows:
            vol_series = realized_vol(pd.Series(close_1x), vw)
            vol_arr = vol_series.values

            for vl in vol_lows:
                for vh in vol_highs:
                    if vl >= vh: continue
                    for vt in vix_thresholds:
                        use_vix = vt < 999
                        ns, ret, mdd = run_lev_switch(
                            close_3x, close_2x, close_1x, vol_arr,
                            vix_arr, vl, vh, vt, use_vix)

                        row = {
                            "trio": f"{sym_3x}/{sym_2x}/{sym_1x}",
                            "vol_window": vw, "vol_low": vl, "vol_high": vh,
                            "vix_thresh": vt if use_vix else "none",
                            "n_switches": ns, "return_pct": ret, "max_dd_pct": mdd,
                            "bh_3x_pct": bh_3x, "bh_1x_pct": bh_1x,
                            "vs_bh_3x": round(ret - bh_3x, 1),
                            "vs_bh_1x": round(ret - bh_1x, 1),
                        }
                        all_results.append(row)

                        if ret > best_ret:
                            best_ret = ret; best_row = row
                        ra = ret / max(abs(mdd), 1)
                        if ra > best_risk_adj:
                            best_risk_adj = ra; best_ra_row = row

        print(f"  Best return: {best_ret:>+10,.1f}% | vw={best_row['vol_window']} "
              f"vol={best_row['vol_low']}/{best_row['vol_high']} vix={best_row['vix_thresh']} "
              f"({best_row['n_switches']} switches, MaxDD {best_row['max_dd_pct']}%) "
              f"vs 3x: {best_row['vs_bh_3x']:+.1f}%")
        print(f"  Best risk-adj: {best_ra_row['return_pct']:>+10,.1f}% | MaxDD {best_ra_row['max_dd_pct']}% "
              f"({best_ra_row['n_switches']} switches)")

    res_df = pd.DataFrame(all_results)
    res_df.to_csv("results/exp3_lev_switch.csv", index=False)
    print(f"\nSaved: results/exp3_lev_switch.csv ({len(all_results)} results)")


if __name__ == "__main__":
    main()
