"""
EXP 2 OOS 검증: ATR Position Sizing
Train: ~2020, Test: 2020~
"""
import pandas as pd
import numpy as np
import os

TOTAL_CASH = 10000.0
FEE_RATE = 0.0025
SPLIT = "2020-01-01"

SYMBOLS = ["SOXL", "TQQQ", "SPXL", "TNA", "QLD", "UWM", "QQQ"]
PARAMS = {
    "SOXL": (25, 60, 55), "TQQQ": (25, 65, 55), "SPXL": (30, 70, 55),
    "TNA": (35, 70, 50), "QLD": (25, 70, 55), "UWM": (25, 70, 50), "QQQ": (25, 75, 55),
}


def rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0); loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period).mean()
    return 100 - (100 / (1 + avg_gain / avg_loss))


def atr(high, low, close, period=14):
    tr = np.maximum(high - low, np.maximum(abs(high - close.shift(1)), abs(low - close.shift(1))))
    return tr.rolling(period).mean()


def bollinger_upper(series, period=20, num_std=2):
    sma = series.rolling(period).mean()
    return sma + num_std * series.rolling(period).std()


def run_atr_sized(close, high, low, rsi_arr, bb_upper, atr_arr,
                  buy_rsi, sell_rsi, rebuy_rsi, risk_pct, atr_mult):
    n = len(close); cash = TOTAL_CASH; shares = 0.0; state = 0
    n_buys = 0; n_sells = 0; peak_val = TOTAL_CASH; max_dd = 0.0

    for i in range(n):
        price = close[i]; rv = rsi_arr[i]; bb = bb_upper[i]; av = atr_arr[i]
        if np.isnan(rv) or np.isnan(bb) or np.isnan(av) or av <= 0:
            val = cash + shares * price
            if val > peak_val: peak_val = val
            continue

        if state == 0 and rv < buy_rsi:
            risk_per_share = av * atr_mult
            max_shares = (cash * risk_pct) / risk_per_share
            buy_value = min(max_shares * price, cash)
            if buy_value > 1:
                shares = buy_value * (1 - FEE_RATE) / price
                cash -= buy_value; n_buys += 1; state = 1
        elif state == 1 and rv > sell_rsi and price > bb:
            cash += shares * price * (1 - FEE_RATE)
            shares = 0; n_sells += 1; state = 2
        elif state == 2 and rv < rebuy_rsi:
            risk_per_share = av * atr_mult
            max_shares = (cash * risk_pct) / risk_per_share
            buy_value = min(max_shares * price, cash)
            if buy_value > 1:
                shares = buy_value * (1 - FEE_RATE) / price
                cash -= buy_value; n_buys += 1; state = 1

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
    print("EXP 2 OOS: ATR POSITION SIZING (train < 2020, test >= 2020)")
    print("=" * 120)

    risk_pcts = [0.01, 0.02, 0.05, 0.10, 0.20, 0.50, 1.0]
    atr_mults = [1.0, 1.5, 2.0, 3.0]
    all_results = []

    for sym in SYMBOLS:
        if not os.path.exists(f"data/{sym}.parquet"): continue
        df = pd.read_parquet(f"data/{sym}.parquet").sort_index()
        df["rsi14"] = rsi(df["close"], 14)
        df["atr14"] = atr(df["high"], df["low"], df["close"], 14)
        df["bb_upper"] = bollinger_upper(df["close"], 20, 2)

        train_idx = df.index[df.index < SPLIT]
        test_idx = df.index[df.index >= SPLIT]

        if len(train_idx) < 200 or len(test_idx) < 200:
            print(f"  SKIP {sym}: insufficient data"); continue

        buy_r, sell_r, rebuy_r = PARAMS[sym]

        print(f"\n{'='*80}")
        print(f"[{sym}] train: {len(train_idx)} bars | test: {len(test_idx)} bars")
        print(f"{'='*80}")

        # ── TRAIN ──
        cl_tr = df.loc[train_idx, "close"].values
        hi_tr = df.loc[train_idx, "high"].values
        lo_tr = df.loc[train_idx, "low"].values
        rsi_tr = df.loc[train_idx, "rsi14"].values
        atr_tr = df.loc[train_idx, "atr14"].values
        bb_tr = df.loc[train_idx, "bb_upper"].values

        bh_tr = run_bh(cl_tr)
        nb0, ns0, rsi_tr_ret, rsi_tr_dd = run_baseline(cl_tr, rsi_tr, bb_tr, buy_r, sell_r, rebuy_r)
        print(f"  TRAIN B&H: {bh_tr:>+10,.1f}% | RSI: {rsi_tr_ret:>+10,.1f}% ({nb0}B/{ns0}S)")

        train_best_ret = rsi_tr_ret
        train_best_params = (1.0, 1.0)  # default: all-in equivalent
        for rp in risk_pcts:
            for am in atr_mults:
                nb, ns, ret, mdd = run_atr_sized(cl_tr, hi_tr, lo_tr, rsi_tr, bb_tr, atr_tr,
                                                  buy_r, sell_r, rebuy_r, rp, am)
                if ret > train_best_ret:
                    train_best_ret = ret
                    train_best_params = (rp, am)

        print(f"  TRAIN best: {train_best_ret:>+10,.1f}% | params: risk={train_best_params[0]} atr_mult={train_best_params[1]}")

        # ── TEST ──
        cl_te = df.loc[test_idx, "close"].values
        hi_te = df.loc[test_idx, "high"].values
        lo_te = df.loc[test_idx, "low"].values
        rsi_te = df.loc[test_idx, "rsi14"].values
        atr_te = df.loc[test_idx, "atr14"].values
        bb_te = df.loc[test_idx, "bb_upper"].values

        bh_te = run_bh(cl_te)
        nb0, ns0, rsi_te_ret, rsi_te_dd = run_baseline(cl_te, rsi_te, bb_te, buy_r, sell_r, rebuy_r)
        print(f"  TEST  B&H: {bh_te:>+10,.1f}% | RSI: {rsi_te_ret:>+10,.1f}% ({nb0}B/{ns0}S, MaxDD {rsi_te_dd}%)")

        # Apply train best to test
        brp, bam = train_best_params
        if brp == 1.0 and bam == 1.0 and train_best_ret == rsi_tr_ret:
            test_ret, test_dd, test_nb, test_ns = rsi_te_ret, rsi_te_dd, nb0, ns0
        else:
            test_nb, test_ns, test_ret, test_dd = run_atr_sized(
                cl_te, hi_te, lo_te, rsi_te, bb_te, atr_te, buy_r, sell_r, rebuy_r, brp, bam)

        print(f"  TEST  train_best applied: {test_ret:>+10,.1f}% ({test_nb}B/{test_ns}S, MaxDD {test_dd}%)")
        print(f"  vs RSI: {test_ret - rsi_te_ret:+.1f}% | vs B&H: {test_ret - bh_te:+.1f}%")

        # All combos on test
        print(f"\n  All test results:")
        print(f"  {'Risk%':<8} {'ATR_m':>6} {'Return%':>10} {'vs RSI':>10} {'MaxDD%':>8} {'B/S':>8}")
        print(f"  {'-'*55}")
        for rp in risk_pcts:
            for am in atr_mults:
                nb, ns, ret, mdd = run_atr_sized(cl_te, hi_te, lo_te, rsi_te, bb_te, atr_te,
                                                  buy_r, sell_r, rebuy_r, rp, am)
                marker = " << train_best" if (rp, am) == train_best_params else ""
                print(f"  {rp:<8} {am:>6.1f} {ret:>+9,.1f}% {ret-rsi_te_ret:>+9,.1f}% {mdd:>7.1f}% {nb}B/{ns}S{marker}")
                all_results.append({
                    "symbol": sym, "risk_pct": rp, "atr_mult": am,
                    "period": "test", "n_buys": nb, "n_sells": ns,
                    "return_pct": ret, "max_dd_pct": mdd,
                    "bh_pct": bh_te, "rsi_pct": rsi_te_ret,
                    "vs_rsi": round(ret - rsi_te_ret, 1), "vs_bh": round(ret - bh_te, 1),
                    "train_best": (rp, am) == train_best_params,
                })

        # Test actual best
        test_results = [(r["risk_pct"], r["atr_mult"], r["return_pct"], r["max_dd_pct"], r["n_buys"], r["n_sells"])
                        for r in all_results if r["symbol"] == sym]
        actual_best = max(test_results, key=lambda x: x[2])
        print(f"\n  TEST actual best: {actual_best[2]:>+10,.1f}% | risk={actual_best[0]} atr_mult={actual_best[1]} "
              f"({actual_best[4]}B/{actual_best[5]}S, MaxDD {actual_best[3]}%)")

    if all_results:
        os.makedirs("results", exist_ok=True)
        pd.DataFrame(all_results).to_csv("results/exp2_atr_sizing_oos.csv", index=False)
        print(f"\nSaved: results/exp2_atr_sizing_oos.csv")


if __name__ == "__main__":
    main()
