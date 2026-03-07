"""
EXP 5 OOS 검증: VIX Term Structure
Train: ~2020, Test: 2020~
"""
import pandas as pd
import numpy as np
import os
import yfinance as yf

TOTAL_CASH = 10000.0
FEE_RATE = 0.0025
SPLIT = "2020-01-01"

SYMBOLS = ["SOXL", "TQQQ", "SPXL", "TNA"]
PARAMS = {
    "SOXL": (25, 60, 55), "TQQQ": (25, 65, 55), "SPXL": (30, 70, 55), "TNA": (35, 70, 50),
}


def rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0); loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period).mean()
    return 100 - (100 / (1 + avg_gain / avg_loss))


def bollinger_upper(series, period=20, num_std=2):
    sma = series.rolling(period).mean()
    return sma + num_std * series.rolling(period).std()


def run_vix_term(close, rsi_arr, bb_upper, vix_ratio, buy_rsi, sell_rsi, rebuy_rsi, mode, ratio_thresh):
    n = len(close); cash = TOTAL_CASH; shares = 0.0; state = 0
    n_buys = 0; n_sells = 0; peak_val = TOTAL_CASH; max_dd = 0.0

    for i in range(n):
        price = close[i]; rv = rsi_arr[i]; bb = bb_upper[i]; vr = vix_ratio[i]
        if np.isnan(rv) or np.isnan(bb) or np.isnan(vr):
            val = cash + shares * price
            if val > peak_val: peak_val = val
            continue

        is_back = vr > ratio_thresh
        is_contango = vr < (1.0 / ratio_thresh)

        if mode == "adjust":
            if is_contango:
                ab, as_, ar = buy_rsi+5, sell_rsi+5, rebuy_rsi+5
            elif is_back:
                ab, as_, ar = buy_rsi-5, sell_rsi-5, rebuy_rsi-5
            else:
                ab, as_, ar = buy_rsi, sell_rsi, rebuy_rsi
            ab = max(10, min(ab, 50)); as_ = max(50, min(as_, 90)); ar = max(15, min(ar, 65))
        else:
            ab, as_, ar = buy_rsi, sell_rsi, rebuy_rsi

        if mode in ("force", "block+force") and is_back and state == 1:
            cash = shares * price * (1 - FEE_RATE); shares = 0; n_sells += 1; state = 2

        if state == 0 and rv < ab:
            blocked = mode in ("block", "block+force") and is_back
            if not blocked:
                shares = cash * (1 - FEE_RATE) / price; cash = 0; n_buys += 1; state = 1
        elif state == 1 and rv > as_ and price > bb:
            cash = shares * price * (1 - FEE_RATE); shares = 0; n_sells += 1; state = 2
        elif state == 2 and rv < ar:
            blocked = mode in ("block", "block+force") and is_back
            if not blocked:
                shares = cash * (1 - FEE_RATE) / price; cash = 0; n_buys += 1; state = 1

        val = cash + shares * price
        if val > peak_val: peak_val = val
        dd = (val - peak_val) / peak_val
        if dd < max_dd: max_dd = dd

    final = cash + shares * close[-1]
    return n_buys, n_sells, round((final / TOTAL_CASH - 1) * 100, 1), round(max_dd * 100, 1)


def run_baseline(close, rsi_arr, bb_upper, buy_rsi, sell_rsi, rebuy_rsi):
    n = len(close); cash = TOTAL_CASH; shares = 0.0; state = 0
    nb = 0; ns = 0; pv = TOTAL_CASH; md = 0.0
    for i in range(n):
        p = close[i]; rv = rsi_arr[i]; bb = bb_upper[i]
        if np.isnan(rv) or np.isnan(bb):
            v = cash + shares * p
            if v > pv: pv = v
            continue
        if state == 0 and rv < buy_rsi:
            shares = cash * (1-FEE_RATE)/p; cash = 0; nb += 1; state = 1
        elif state == 1 and rv > sell_rsi and p > bb:
            cash = shares * p * (1-FEE_RATE); shares = 0; ns += 1; state = 2
        elif state == 2 and rv < rebuy_rsi:
            shares = cash * (1-FEE_RATE)/p; cash = 0; nb += 1; state = 1
        v = cash + shares * p
        if v > pv: pv = v
        d = (v - pv) / pv
        if d < md: md = d
    return nb, ns, round((cash + shares * close[-1]) / TOTAL_CASH * 100 - 100, 1), round(md * 100, 1)


def run_bh(close):
    return round((TOTAL_CASH * (1-FEE_RATE) / close[0] * close[-1] / TOTAL_CASH - 1) * 100, 1)


def main():
    print("=" * 120)
    print("EXP 5 OOS: VIX TERM STRUCTURE (train < 2020, test >= 2020)")
    print("=" * 120)

    # Load VIX data
    vix = pd.read_parquet("data/^VIX.parquet").sort_index()
    vix3m_path = "data/^VIX3M.parquet"
    if not os.path.exists(vix3m_path):
        df = yf.download("^VIX3M", period="max", progress=False, auto_adjust=True)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df.columns = [c.lower() for c in df.columns]
        df.to_parquet(vix3m_path)
    vix3m = pd.read_parquet(vix3m_path).sort_index()

    modes = ["block", "force", "block+force", "adjust"]
    ratio_thresholds = [1.0, 1.05, 1.10, 1.15, 1.20]

    for sym in SYMBOLS:
        if not os.path.exists(f"data/{sym}.parquet"): continue
        df = pd.read_parquet(f"data/{sym}.parquet").sort_index()
        df["rsi14"] = rsi(df["close"], 14)
        df["bb_upper"] = bollinger_upper(df["close"], 20, 2)

        common = df.index.intersection(vix.index).intersection(vix3m.index).sort_values()
        train_idx = common[common < SPLIT]
        test_idx = common[common >= SPLIT]

        if len(train_idx) < 200 or len(test_idx) < 200:
            print(f"  SKIP {sym}: insufficient data"); continue

        buy_r, sell_r, rebuy_r = PARAMS[sym]

        print(f"\n{'='*80}")
        print(f"[{sym}] train: {len(train_idx)} bars | test: {len(test_idx)} bars")
        print(f"{'='*80}")

        # ── TRAIN ──
        close_tr = df.loc[train_idx, "close"].values
        rsi_tr = df.loc[train_idx, "rsi14"].values
        bb_tr = df.loc[train_idx, "bb_upper"].values
        vr_tr = (vix.loc[train_idx, "close"] / vix3m.loc[train_idx, "close"]).values

        bh_tr = run_bh(close_tr)
        nb0, ns0, rsi_tr_ret, rsi_tr_dd = run_baseline(close_tr, rsi_tr, bb_tr, buy_r, sell_r, rebuy_r)
        print(f"  TRAIN B&H: {bh_tr:>+10,.1f}% | RSI: {rsi_tr_ret:>+10,.1f}% ({nb0}B/{ns0}S)")

        train_best_ret = rsi_tr_ret
        train_best_params = ("none", 0)
        for mode in modes:
            for rt in ratio_thresholds:
                nb, ns, ret, mdd = run_vix_term(close_tr, rsi_tr, bb_tr, vr_tr, buy_r, sell_r, rebuy_r, mode, rt)
                if ret > train_best_ret:
                    train_best_ret = ret
                    train_best_params = (mode, rt)

        print(f"  TRAIN best: {train_best_ret:>+10,.1f}% | params: {train_best_params}")

        # ── TEST ──
        close_te = df.loc[test_idx, "close"].values
        rsi_te = df.loc[test_idx, "rsi14"].values
        bb_te = df.loc[test_idx, "bb_upper"].values
        vr_te = (vix.loc[test_idx, "close"] / vix3m.loc[test_idx, "close"]).values

        bh_te = run_bh(close_te)
        nb0, ns0, rsi_te_ret, rsi_te_dd = run_baseline(close_te, rsi_te, bb_te, buy_r, sell_r, rebuy_r)
        print(f"  TEST  B&H: {bh_te:>+10,.1f}% | RSI: {rsi_te_ret:>+10,.1f}% ({nb0}B/{ns0}S, MaxDD {rsi_te_dd}%)")

        # Apply train best to test
        bmode, brt = train_best_params
        if bmode == "none":
            test_ret, test_dd, test_nb, test_ns = rsi_te_ret, rsi_te_dd, nb0, ns0
        else:
            test_nb, test_ns, test_ret, test_dd = run_vix_term(
                close_te, rsi_te, bb_te, vr_te, buy_r, sell_r, rebuy_r, bmode, brt)

        print(f"  TEST  train_best applied: {test_ret:>+10,.1f}% ({test_nb}B/{test_ns}S, MaxDD {test_dd}%)")
        print(f"  vs RSI: {test_ret - rsi_te_ret:+.1f}% | vs B&H: {test_ret - bh_te:+.1f}%")

        # All combos on test
        print(f"\n  All test results:")
        print(f"  {'Mode':<15} {'Ratio':>6} {'Return%':>10} {'vs RSI':>10} {'MaxDD%':>8} {'B/S':>8}")
        print(f"  {'-'*60}")
        for mode in modes:
            for rt in ratio_thresholds:
                nb, ns, ret, mdd = run_vix_term(close_te, rsi_te, bb_te, vr_te, buy_r, sell_r, rebuy_r, mode, rt)
                marker = " ◀ train_best" if (mode, rt) == train_best_params else ""
                print(f"  {mode:<15} {rt:>6.2f} {ret:>+9,.1f}% {ret-rsi_te_ret:>+9,.1f}% {mdd:>7.1f}% {nb}B/{ns}S{marker}")

        # Test actual best
        test_results = []
        for mode in modes:
            for rt in ratio_thresholds:
                nb, ns, ret, mdd = run_vix_term(close_te, rsi_te, bb_te, vr_te, buy_r, sell_r, rebuy_r, mode, rt)
                test_results.append((mode, rt, nb, ns, ret, mdd))
        actual_best = max(test_results, key=lambda x: x[4])
        print(f"\n  TEST actual best: {actual_best[4]:>+10,.1f}% | {actual_best[0]} ratio>{actual_best[1]} "
              f"({actual_best[2]}B/{actual_best[3]}S, MaxDD {actual_best[5]}%)")


if __name__ == "__main__":
    main()
