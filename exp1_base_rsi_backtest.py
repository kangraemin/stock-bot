"""
실험 1: 기초자산 RSI로 레버리지 ETF 매매
- SOXX RSI → SOXL 매매, QQQ RSI → TQQQ 매매, SPY RSI → SPXL 매매, IWM RSI → TNA 매매
- 레버리지 ETF는 변동성 드래그로 RSI가 왜곡 → 기초자산 RSI가 더 깨끗
"""
import pandas as pd
import numpy as np
import os, time

TOTAL_CASH = 10000.0
FEE_RATE = 0.0025

PAIRS = [
    ("SOXL", "SOXX"), ("TQQQ", "QQQ"), ("SPXL", "SPY"), ("TNA", "IWM"),
]

# 각 페어별 RSI 파라미터 (기존 그리드 서치 최적값)
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


def run_backtest(trade_close, signal_rsi, trade_bb, buy_rsi, sell_rsi, rebuy_rsi):
    n = len(trade_close)
    cash = TOTAL_CASH
    shares = 0.0
    state = 0
    n_buys = 0; n_sells = 0
    peak_val = TOTAL_CASH; max_dd = 0.0

    for i in range(n):
        price = trade_close[i]
        rv = signal_rsi[i]
        bb = trade_bb[i]
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

    final = cash + shares * trade_close[-1]
    ret = (final / TOTAL_CASH - 1) * 100
    return n_buys, n_sells, round(ret, 1), round(max_dd * 100, 1)


def run_bh(close):
    shares = TOTAL_CASH * (1 - FEE_RATE) / close[0]
    return round((shares * close[-1] / TOTAL_CASH - 1) * 100, 1)


def main():
    print("=" * 120)
    print("EXP 1: BASE ASSET RSI → LEVERAGED ETF TRADE")
    print("=" * 120)

    all_results = []
    buy_rsi_grid = [20, 25, 30, 35, 40, 45]
    sell_rsi_grid = [55, 60, 65, 70, 75, 80]
    rebuy_rsi_grid = [30, 40, 50, 55, 60]

    for lev_sym, base_sym in PAIRS:
        if not os.path.exists(f"data/{lev_sym}.parquet") or not os.path.exists(f"data/{base_sym}.parquet"):
            continue

        lev_df = pd.read_parquet(f"data/{lev_sym}.parquet").sort_index()
        base_df = pd.read_parquet(f"data/{base_sym}.parquet").sort_index()

        common_idx = lev_df.index.intersection(base_df.index).sort_values()
        lev_df = lev_df.loc[common_idx]
        base_df = base_df.loc[common_idx]

        # Indicators
        lev_rsi = rsi(lev_df["close"], 14).values
        base_rsi = rsi(base_df["close"], 14).values
        lev_bb = bollinger_upper(lev_df["close"], 20, 2).values
        lev_close = lev_df["close"].values

        bh_ret = run_bh(lev_close)
        buy_r, sell_r, rebuy_r = PARAMS[lev_sym]

        # Baseline: lev RSI → lev trade
        nb, ns, lev_rsi_ret, lev_rsi_dd = run_backtest(lev_close, lev_rsi, lev_bb, buy_r, sell_r, rebuy_r)
        # Base RSI → lev trade (same params)
        nb2, ns2, base_rsi_ret, base_rsi_dd = run_backtest(lev_close, base_rsi, lev_bb, buy_r, sell_r, rebuy_r)

        print(f"\n[{lev_sym}/{base_sym}] {len(common_idx)} bars")
        print(f"  B&H:          {bh_ret:>+12,.1f}%")
        print(f"  Lev RSI:      {lev_rsi_ret:>+12,.1f}% ({nb}B/{ns}S, MaxDD {lev_rsi_dd}%)")
        print(f"  Base RSI:     {base_rsi_ret:>+12,.1f}% ({nb2}B/{ns2}S, MaxDD {base_rsi_dd}%)")
        print(f"  Improvement:  {base_rsi_ret - lev_rsi_ret:>+12,.1f}%")

        # Grid search: base RSI with different thresholds
        best_ret = -999
        best_row = None
        for br in buy_rsi_grid:
            for sr in sell_rsi_grid:
                if br >= sr: continue
                for rr in rebuy_rsi_grid:
                    # Base RSI signal
                    nb, ns, ret, mdd = run_backtest(lev_close, base_rsi, lev_bb, br, sr, rr)
                    row = {
                        "lev": lev_sym, "base": base_sym, "signal_source": "base_rsi",
                        "buy_rsi": br, "sell_rsi": sr, "rebuy_rsi": rr,
                        "n_buys": nb, "n_sells": ns, "return_pct": ret, "max_dd_pct": mdd,
                        "bh_pct": bh_ret, "vs_bh": round(ret - bh_ret, 1),
                    }
                    all_results.append(row)
                    if ret > best_ret:
                        best_ret = ret; best_row = row

                    # Lev RSI signal (for comparison)
                    nb, ns, ret, mdd = run_backtest(lev_close, lev_rsi, lev_bb, br, sr, rr)
                    row2 = {
                        "lev": lev_sym, "base": base_sym, "signal_source": "lev_rsi",
                        "buy_rsi": br, "sell_rsi": sr, "rebuy_rsi": rr,
                        "n_buys": nb, "n_sells": ns, "return_pct": ret, "max_dd_pct": mdd,
                        "bh_pct": bh_ret, "vs_bh": round(ret - bh_ret, 1),
                    }
                    all_results.append(row2)

        print(f"  Grid best (base RSI): {best_ret:>+12,.1f}% | "
              f"buy={best_row['buy_rsi']} sell={best_row['sell_rsi']} rebuy={best_row['rebuy_rsi']} "
              f"({best_row['n_buys']}B/{best_row['n_sells']}S, MaxDD {best_row['max_dd_pct']}%)")

    res_df = pd.DataFrame(all_results)
    res_df.to_csv("results/exp1_base_rsi.csv", index=False)

    # Summary: base_rsi vs lev_rsi head-to-head
    print(f"\n{'='*100}")
    print("HEAD-TO-HEAD: Base RSI vs Lev RSI (same params)")
    print(f"{'='*100}")
    for lev_sym, base_sym in PAIRS:
        sub = res_df[res_df["lev"] == lev_sym]
        if sub.empty: continue
        base_best = sub[sub["signal_source"] == "base_rsi"].loc[sub[sub["signal_source"] == "base_rsi"]["return_pct"].idxmax()]
        lev_best = sub[sub["signal_source"] == "lev_rsi"].loc[sub[sub["signal_source"] == "lev_rsi"]["return_pct"].idxmax()]

        # Same-param comparison
        base_wins = 0; lev_wins = 0; total = 0
        for (br, sr, rr), grp in sub.groupby(["buy_rsi", "sell_rsi", "rebuy_rsi"]):
            if len(grp) < 2: continue
            b = grp[grp["signal_source"] == "base_rsi"]["return_pct"].values
            l = grp[grp["signal_source"] == "lev_rsi"]["return_pct"].values
            if len(b) > 0 and len(l) > 0:
                total += 1
                if b[0] > l[0]: base_wins += 1
                elif l[0] > b[0]: lev_wins += 1

        print(f"  {lev_sym}/{base_sym}: base_rsi wins {base_wins}/{total} ({base_wins/total*100:.0f}%) | "
              f"best base: {base_best['return_pct']:>+10,.1f}% ({base_best['n_buys']}B/{base_best['n_sells']}S) | "
              f"best lev: {lev_best['return_pct']:>+10,.1f}% ({lev_best['n_buys']}B/{lev_best['n_sells']}S)")

    print(f"\nSaved: results/exp1_base_rsi.csv")


if __name__ == "__main__":
    main()
