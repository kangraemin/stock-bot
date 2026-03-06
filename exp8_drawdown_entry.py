"""
실험 8: Drawdown-Based Entry (ATH 대비 하락률 분할매수)
- ATH 대비 -20/-30/-40/-50% 단계별 분할매수
- 회복 시 trailing stop으로 매도
- 그리드: 진입 설정, trailing stop %, exit mode
"""
import pandas as pd
import numpy as np
import os

TOTAL_CASH = 10000.0
FEE_RATE = 0.0025

SYMBOLS = ["SOXL", "TQQQ", "SPXL", "TNA"]

ENTRY_CONFIGS = [
    ("2step", [-0.20, -0.40], [0.50, 0.50]),
    ("3step", [-0.20, -0.30, -0.40], [0.33, 0.33, 0.34]),
    ("4step", [-0.15, -0.25, -0.35, -0.50], [0.25, 0.25, 0.25, 0.25]),
    ("5step", [-0.10, -0.20, -0.30, -0.40, -0.50], [0.20, 0.20, 0.20, 0.20, 0.20]),
    ("aggressive", [-0.10, -0.20, -0.30], [0.40, 0.35, 0.25]),
    ("conservative", [-0.30, -0.40, -0.50], [0.30, 0.30, 0.40]),
]

TRAILING_STOPS = [0.03, 0.05, 0.07, 0.10, 0.15]
EXIT_MODES = ["trailing", "ath_recover", "both"]


def run_drawdown_entry(close, thresholds, weights, trailing_pct, exit_mode):
    n = len(close)
    cash = TOTAL_CASH
    shares = 0.0
    n_buys = 0; n_sells = 0
    peak_val = TOTAL_CASH; max_dd = 0.0
    ath = close[0]
    entry_peak = 0.0
    total_steps = len(thresholds)
    invested = [False] * total_steps
    steps_used = 0

    for i in range(n):
        price = close[i]
        if price > ath:
            ath = price

        drawdown = (price - ath) / ath

        # Buy: check each step
        for step_idx in range(steps_used, total_steps):
            if not invested[step_idx] and drawdown <= thresholds[step_idx]:
                invest_amt = min(TOTAL_CASH * weights[step_idx], cash)
                if invest_amt > 1:
                    shares += invest_amt * (1 - FEE_RATE) / price
                    cash -= invest_amt
                    n_buys += 1
                    invested[step_idx] = True
                    steps_used += 1
                    entry_peak = max(entry_peak, price)

        # Sell logic
        if shares > 0:
            if price > entry_peak:
                entry_peak = price

            should_sell = False
            if exit_mode in ("trailing", "both"):
                if entry_peak > 0 and (price - entry_peak) / entry_peak < -trailing_pct:
                    should_sell = True
            if exit_mode in ("ath_recover", "both"):
                if price >= ath * 0.98:
                    should_sell = True

            if should_sell:
                cash += shares * price * (1 - FEE_RATE)
                shares = 0; n_sells += 1
                steps_used = 0
                invested = [False] * total_steps
                entry_peak = 0.0

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
    print("EXP 8: DRAWDOWN-BASED ENTRY (ATH 대비 분할매수)")
    print("=" * 120)

    all_results = []

    for sym in SYMBOLS:
        path = f"data/{sym}.parquet"
        if not os.path.exists(path):
            continue

        df = pd.read_parquet(path).sort_index()
        close = df["close"].values
        bh_ret = run_bh(close)

        print(f"\n[{sym}] {len(close)} bars | B&H: {bh_ret:+.1f}%")

        best_ret = -999; best_row = None
        best_risk = -999; best_risk_row = None

        for config_name, thresholds, weights in ENTRY_CONFIGS:
            for ts in TRAILING_STOPS:
                for em in EXIT_MODES:
                    nb, ns, ret, mdd = run_drawdown_entry(
                        close, thresholds, weights, ts, em)

                    row = {
                        "symbol": sym, "config": config_name,
                        "thresholds": str(thresholds), "weights": str(weights),
                        "trailing_pct": ts, "exit_mode": em,
                        "n_buys": nb, "n_sells": ns,
                        "return_pct": ret, "max_dd_pct": mdd,
                        "bh_pct": bh_ret,
                        "vs_bh": round(ret - bh_ret, 1),
                    }
                    all_results.append(row)

                    if ret > best_ret:
                        best_ret = ret; best_row = row
                    risk_adj = ret / max(abs(mdd), 1)
                    if risk_adj > best_risk:
                        best_risk = risk_adj; best_risk_row = row

        print(f"  Best return:   {best_ret:>+10,.1f}% | {best_row['config']} "
              f"trail={best_row['trailing_pct']} exit={best_row['exit_mode']} "
              f"({best_row['n_buys']}B/{best_row['n_sells']}S, MaxDD {best_row['max_dd_pct']}%)")
        if best_risk_row:
            print(f"  Best risk-adj: {best_risk_row['return_pct']:>+10,.1f}% | {best_risk_row['config']} "
                  f"trail={best_risk_row['trailing_pct']} exit={best_risk_row['exit_mode']} "
                  f"(MaxDD {best_risk_row['max_dd_pct']}%)")

    res_df = pd.DataFrame(all_results)
    res_df.to_csv("results/exp8_drawdown_entry.csv", index=False)
    print(f"\nSaved: results/exp8_drawdown_entry.csv ({len(all_results)} rows)")


if __name__ == "__main__":
    main()
