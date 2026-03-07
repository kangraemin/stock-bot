"""
매크로 레짐 심층 백테스트 (3-in-1)
1. Out-of-sample 검증: 2020년 전/후 분리
2. 매크로 지표 ablation: 6개 지표 개별/조합 기여도
3. 실전용 단순 전략: alert.py에 바로 적용 가능한 레짐 필터
"""
import pandas as pd
import numpy as np
import os
import time
from itertools import combinations

TOTAL_CASH = 10000.0
FEE_RATE = 0.0025
SPLIT_DATE = "2020-01-01"

MACRO_SYMBOLS = {
    "copper": "HG=F",
    "oil": "CL=F",
    "vix": "^VIX",
    "gold": "GC=F",
    "tnx": "^TNX",
    "dollar": "DX-Y.NYB",
}

PAIRS = [
    ("SOXL", "SOXX", 25, 60, 55),
    ("TQQQ", "QQQ", 25, 65, 55),
    ("SPXL", "SPY", 30, 70, 55),
    ("TNA", "IWM", 35, 70, 50),
]


def load_macro():
    frames = {}
    for name, sym in MACRO_SYMBOLS.items():
        path = f"data/{sym}.parquet"
        if not os.path.exists(path):
            continue
        df = pd.read_parquet(path).sort_index()
        frames[name] = df["close"]
    return pd.DataFrame(frames).sort_index().ffill()


def compute_indicator_signal(macro, name, lookback):
    """개별 지표의 시그널 계산"""
    s = pd.Series(0.0, index=macro.index)

    if name == "copper" and "copper" in macro.columns:
        sma = macro["copper"].rolling(lookback).mean()
        s = pd.Series(np.where(macro["copper"] > sma, 1, -1), index=macro.index)

    elif name == "oil" and "oil" in macro.columns:
        oil_ret = macro["oil"].pct_change(lookback)
        s = pd.Series(np.where(oil_ret < -0.15, -1, np.where(oil_ret > 0.1, 0.5, 0)), index=macro.index)

    elif name == "vix" and "vix" in macro.columns:
        sma = macro["vix"].rolling(lookback).mean()
        vix_sig = np.where(macro["vix"] < sma * 0.9, 1, np.where(macro["vix"] > sma * 1.1, -1, 0))
        vix_ext = np.where(macro["vix"] > 30, -1, 0)
        s = pd.Series(vix_sig + vix_ext, index=macro.index)

    elif name == "gold" and "gold" in macro.columns:
        gold_ret = macro["gold"].pct_change(lookback)
        s = pd.Series(np.where(gold_ret > 0.1, -0.5, np.where(gold_ret < -0.05, 0.5, 0)), index=macro.index)

    elif name == "tnx" and "tnx" in macro.columns:
        tnx_chg = macro["tnx"].diff(lookback)
        s = pd.Series(np.where(tnx_chg > 0.5, -1, np.where(tnx_chg < -0.3, 0.5, 0)), index=macro.index)

    elif name == "dollar" and "dollar" in macro.columns:
        sma = macro["dollar"].rolling(lookback).mean()
        s = pd.Series(np.where(macro["dollar"] > sma * 1.02, -1,
                      np.where(macro["dollar"] < sma * 0.98, 1, 0)), index=macro.index)

    return s.values


def compute_regime_from_indicators(macro, indicator_names, lookback, ron_th, roff_th):
    """선택된 지표들만으로 레짐 계산"""
    score = np.zeros(len(macro))
    for name in indicator_names:
        score += compute_indicator_signal(macro, name, lookback)

    regimes = []
    for s in score:
        if np.isnan(s):
            regimes.append("NEUTRAL")
        elif s >= ron_th:
            regimes.append("RISK_ON")
        elif s <= roff_th:
            regimes.append("RISK_OFF")
        else:
            regimes.append("NEUTRAL")
    return regimes


def apply_confirmation(raw_regimes, confirm_days):
    if confirm_days <= 1:
        return raw_regimes
    n = len(raw_regimes)
    confirmed = [raw_regimes[0]] * n
    streak = 1
    prev_raw = raw_regimes[0]
    current = raw_regimes[0]
    for i in range(1, n):
        if raw_regimes[i] == prev_raw:
            streak += 1
        else:
            streak = 1
            prev_raw = raw_regimes[i]
        if streak >= confirm_days:
            current = raw_regimes[i]
        confirmed[i] = current
    return confirmed


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


def run_rsi_with_regime_filter(close, rsi_arr, bb_upper, regimes,
                                buy_rsi, sell_rsi, rebuy_rsi, mode):
    """
    mode:
      "none" = RSI only (no regime)
      "block" = Risk-Off시 매수 차단
      "block+force" = 매수차단 + 강제매도
      "adjust" = RSI 임계값 ±10 조정
    """
    n = len(close)
    cash = TOTAL_CASH
    shares = 0.0
    state = 0
    n_buys = 0
    n_sells = 0
    peak_val = TOTAL_CASH
    max_dd = 0.0

    for i in range(n):
        price = close[i]
        rv = rsi_arr[i]
        bb = bb_upper[i]
        regime = regimes[i] if regimes is not None else "NEUTRAL"

        if np.isnan(rv) or np.isnan(bb):
            val = cash + shares * price
            if val > peak_val: peak_val = val
            continue

        # Adjust thresholds
        if mode == "adjust":
            if regime == "RISK_ON":
                adj_buy, adj_sell, adj_rebuy = buy_rsi + 10, sell_rsi + 10, rebuy_rsi + 10
            elif regime == "RISK_OFF":
                adj_buy, adj_sell, adj_rebuy = buy_rsi - 10, sell_rsi - 10, rebuy_rsi - 10
            else:
                adj_buy, adj_sell, adj_rebuy = buy_rsi, sell_rsi, rebuy_rsi
            adj_buy = max(5, min(adj_buy, 50))
            adj_sell = max(50, min(adj_sell, 90))
            adj_rebuy = max(10, min(adj_rebuy, 70))
        else:
            adj_buy, adj_sell, adj_rebuy = buy_rsi, sell_rsi, rebuy_rsi

        # Force sell
        if mode == "block+force" and regime == "RISK_OFF" and state == 1:
            cash = shares * price * (1 - FEE_RATE)
            shares = 0; n_sells += 1; state = 2

        if state == 0:
            if rv < adj_buy:
                if mode in ("block", "block+force") and regime == "RISK_OFF":
                    pass
                else:
                    shares = cash * (1 - FEE_RATE) / price
                    cash = 0; n_buys += 1; state = 1

        elif state == 1:
            if rv > adj_sell and price > bb:
                cash = shares * price * (1 - FEE_RATE)
                shares = 0; n_sells += 1; state = 2

        elif state == 2:
            if rv < adj_rebuy:
                if mode in ("block", "block+force") and regime == "RISK_OFF":
                    pass
                else:
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
    final = shares * close[-1]
    return round((final / TOTAL_CASH - 1) * 100, 1)


def main():
    macro = load_macro()
    all_indicators = ["copper", "oil", "vix", "gold", "tnx", "dollar"]
    available = [i for i in all_indicators if i in macro.columns]
    print(f"Available macro indicators: {available}")

    os.makedirs("results", exist_ok=True)

    # ══════════════════════════════════════════════════════════════
    # PART 1: OUT-OF-SAMPLE VALIDATION
    # ══════════════════════════════════════════════════════════════
    print(f"\n{'='*130}")
    print("PART 1: OUT-OF-SAMPLE VALIDATION (train < 2020, test >= 2020)")
    print(f"{'='*130}")

    oos_results = []
    best_params = {}  # per pair: best params from train set

    modes = ["none", "block", "block+force", "adjust"]
    lookbacks = [20, 50, 100]
    thresholds = [(1.0, -1.0), (1.5, -1.5), (2.0, -2.0), (2.5, -2.5)]
    confirm_days_list = [1, 5, 10]

    for lev_sym, base_sym, buy_rsi, sell_rsi, rebuy_rsi in PAIRS:
        if not os.path.exists(f"data/{lev_sym}.parquet"):
            continue

        lev_df = pd.read_parquet(f"data/{lev_sym}.parquet").sort_index()
        lev_df["rsi14"] = rsi(lev_df["close"], 14)
        lev_df["bb_upper"] = bollinger_upper(lev_df["close"], 20, 2)

        common_idx = macro.index.intersection(lev_df.index).sort_values()
        train_idx = common_idx[common_idx < SPLIT_DATE]
        test_idx = common_idx[common_idx >= SPLIT_DATE]

        if len(train_idx) < 200 or len(test_idx) < 200:
            print(f"  SKIP {lev_sym}: insufficient data (train={len(train_idx)}, test={len(test_idx)})")
            continue

        print(f"\n[{lev_sym}] train: {len(train_idx)} bars ({train_idx[0].strftime('%Y-%m-%d')}~{train_idx[-1].strftime('%Y-%m-%d')}) | "
              f"test: {len(test_idx)} bars ({test_idx[0].strftime('%Y-%m-%d')}~{test_idx[-1].strftime('%Y-%m-%d')})")

        # Train
        train_best_ret = -999
        train_best_params = None

        for mode in modes:
            if mode == "none":
                # RSI only baseline
                close_t = lev_df.loc[train_idx, "close"].values
                rsi_t = lev_df.loc[train_idx, "rsi14"].values
                bb_t = lev_df.loc[train_idx, "bb_upper"].values
                nb, ns, ret, mdd = run_rsi_with_regime_filter(
                    close_t, rsi_t, bb_t, None, buy_rsi, sell_rsi, rebuy_rsi, "none")
                oos_results.append({
                    "pair": f"{lev_sym}/{base_sym}", "period": "train", "mode": "none",
                    "lookback": "-", "threshold": "-", "confirm": "-",
                    "n_buys": nb, "n_sells": ns, "return_pct": ret, "max_dd_pct": mdd,
                })
                if ret > train_best_ret:
                    train_best_ret = ret
                    train_best_params = ("none", "-", "-", "-")
                continue

            for lb in lookbacks:
                for ron_th, roff_th in thresholds:
                    for cd in confirm_days_list:
                        raw = compute_regime_from_indicators(macro.loc[train_idx], available, lb, ron_th, roff_th)
                        regimes = apply_confirmation(raw, cd)

                        close_t = lev_df.loc[train_idx, "close"].values
                        rsi_t = lev_df.loc[train_idx, "rsi14"].values
                        bb_t = lev_df.loc[train_idx, "bb_upper"].values

                        nb, ns, ret, mdd = run_rsi_with_regime_filter(
                            close_t, rsi_t, bb_t, regimes, buy_rsi, sell_rsi, rebuy_rsi, mode)

                        oos_results.append({
                            "pair": f"{lev_sym}/{base_sym}", "period": "train", "mode": mode,
                            "lookback": lb, "threshold": f"{ron_th}/{roff_th}", "confirm": cd,
                            "n_buys": nb, "n_sells": ns, "return_pct": ret, "max_dd_pct": mdd,
                        })
                        if ret > train_best_ret:
                            train_best_ret = ret
                            train_best_params = (mode, lb, (ron_th, roff_th), cd)

        best_params[lev_sym] = train_best_params
        print(f"  Train best: {train_best_ret:>+10,.1f}% | params: {train_best_params}")

        # Test with best params from train
        close_test = lev_df.loc[test_idx, "close"].values
        rsi_test = lev_df.loc[test_idx, "rsi14"].values
        bb_test = lev_df.loc[test_idx, "bb_upper"].values
        bh_test = run_bh(close_test)

        # RSI baseline on test
        nb, ns, rsi_test_ret, rsi_test_dd = run_rsi_with_regime_filter(
            close_test, rsi_test, bb_test, None, buy_rsi, sell_rsi, rebuy_rsi, "none")
        print(f"  Test B&H: {bh_test:>+10,.1f}% | Test RSI only: {rsi_test_ret:>+10,.1f}% ({nb}B/{ns}S)")

        # Best params on test
        bmode, blb, bth, bcd = train_best_params
        if bmode == "none":
            test_ret, test_dd, test_nb, test_ns = rsi_test_ret, rsi_test_dd, nb, ns
        else:
            ron_th, roff_th = bth
            raw = compute_regime_from_indicators(macro.loc[test_idx], available, blb, ron_th, roff_th)
            regimes = apply_confirmation(raw, bcd)
            test_nb, test_ns, test_ret, test_dd = run_rsi_with_regime_filter(
                close_test, rsi_test, bb_test, regimes, buy_rsi, sell_rsi, rebuy_rsi, bmode)

        oos_results.append({
            "pair": f"{lev_sym}/{base_sym}", "period": "test_best", "mode": bmode,
            "lookback": blb, "threshold": f"{bth[0]}/{bth[1]}" if bmode != "none" else "-",
            "confirm": bcd, "n_buys": test_nb, "n_sells": test_ns,
            "return_pct": test_ret, "max_dd_pct": test_dd,
        })

        # All modes on test for comparison
        for mode in modes:
            if mode == "none":
                continue
            for lb in lookbacks:
                for ron_th, roff_th in thresholds:
                    for cd in confirm_days_list:
                        raw = compute_regime_from_indicators(macro.loc[test_idx], available, lb, ron_th, roff_th)
                        regimes = apply_confirmation(raw, cd)
                        nb, ns, ret, mdd = run_rsi_with_regime_filter(
                            close_test, rsi_test, bb_test, regimes, buy_rsi, sell_rsi, rebuy_rsi, mode)
                        oos_results.append({
                            "pair": f"{lev_sym}/{base_sym}", "period": "test", "mode": mode,
                            "lookback": lb, "threshold": f"{ron_th}/{roff_th}", "confirm": cd,
                            "n_buys": nb, "n_sells": ns, "return_pct": ret, "max_dd_pct": mdd,
                        })

        print(f"  Test best_from_train: {test_ret:>+10,.1f}% ({test_nb}B/{test_ns}S, MaxDD {test_dd}%) | "
              f"vs RSI: {test_ret - rsi_test_ret:+.1f}% | vs B&H: {test_ret - bh_test:+.1f}%")

        # Find actual best on test
        test_rows = [r for r in oos_results if r["pair"] == f"{lev_sym}/{base_sym}" and r["period"] == "test"]
        if test_rows:
            actual_best = max(test_rows, key=lambda r: r["return_pct"])
            print(f"  Test actual best: {actual_best['return_pct']:>+10,.1f}% | {actual_best['mode']} "
                  f"lb={actual_best['lookback']} th={actual_best['threshold']} cd={actual_best['confirm']} "
                  f"({actual_best['n_buys']}B/{actual_best['n_sells']}S)")

    # ══════════════════════════════════════════════════════════════
    # PART 2: ABLATION STUDY
    # ══════════════════════════════════════════════════════════════
    print(f"\n\n{'='*130}")
    print("PART 2: ABLATION STUDY (individual indicator contribution)")
    print(f"{'='*130}")

    ablation_results = []
    # Best overall params from Part 1
    best_lb = 50
    best_cd = 10

    for lev_sym, base_sym, buy_rsi, sell_rsi, rebuy_rsi in PAIRS:
        if not os.path.exists(f"data/{lev_sym}.parquet"):
            continue

        lev_df = pd.read_parquet(f"data/{lev_sym}.parquet").sort_index()
        lev_df["rsi14"] = rsi(lev_df["close"], 14)
        lev_df["bb_upper"] = bollinger_upper(lev_df["close"], 20, 2)

        common_idx = macro.index.intersection(lev_df.index).sort_values()
        close = lev_df.loc[common_idx, "close"].values
        rsi_arr_v = lev_df.loc[common_idx, "rsi14"].values
        bb_arr = lev_df.loc[common_idx, "bb_upper"].values

        # RSI baseline
        nb0, ns0, ret0, dd0 = run_rsi_with_regime_filter(
            close, rsi_arr_v, bb_arr, None, buy_rsi, sell_rsi, rebuy_rsi, "none")
        bh_ret = run_bh(close)

        print(f"\n[{lev_sym}] B&H: {bh_ret:>+10,.1f}% | RSI only: {ret0:>+10,.1f}% ({nb0}B/{ns0}S)")

        # Single indicator
        print(f"  {'Indicator':<12} {'block':>12} {'block+force':>15} {'adjust':>12} | (B/S for best)")
        for ind in available:
            best_for_ind = {"mode": "", "ret": -999, "nb": 0, "ns": 0}
            row_data = {"pair": f"{lev_sym}/{base_sym}", "indicator": ind}
            for mode in ["block", "block+force", "adjust"]:
                # Try multiple thresholds
                best_mode_ret = -999
                best_mode_nb, best_mode_ns = 0, 0
                for ron_th, roff_th in [(0.5, -0.5), (1.0, -1.0)]:
                    raw = compute_regime_from_indicators(macro.loc[common_idx], [ind], best_lb, ron_th, roff_th)
                    regimes = apply_confirmation(raw, best_cd)
                    nb, ns, ret, mdd = run_rsi_with_regime_filter(
                        close, rsi_arr_v, bb_arr, regimes, buy_rsi, sell_rsi, rebuy_rsi, mode)
                    if ret > best_mode_ret:
                        best_mode_ret = ret
                        best_mode_nb, best_mode_ns = nb, ns
                row_data[f"{mode}_ret"] = best_mode_ret
                row_data[f"{mode}_vs_rsi"] = round(best_mode_ret - ret0, 1)
                if best_mode_ret > best_for_ind["ret"]:
                    best_for_ind = {"mode": mode, "ret": best_mode_ret, "nb": best_mode_nb, "ns": best_mode_ns}

            row_data["best_mode"] = best_for_ind["mode"]
            row_data["best_ret"] = best_for_ind["ret"]
            row_data["best_vs_rsi"] = round(best_for_ind["ret"] - ret0, 1)
            row_data["rsi_only"] = ret0
            row_data["bh"] = bh_ret
            ablation_results.append(row_data)

            print(f"  {ind:<12} {row_data['block_vs_rsi']:>+11.1f}% {row_data['block+force_vs_rsi']:>+14.1f}% "
                  f"{row_data['adjust_vs_rsi']:>+11.1f}% | best: {best_for_ind['mode']:<13} "
                  f"{best_for_ind['ret']:>+10,.1f}% ({best_for_ind['nb']}B/{best_for_ind['ns']}S)")

        # Combinations of 2
        print(f"\n  Top indicator pairs:")
        pair_results = []
        for combo in combinations(available, 2):
            best_combo_ret = -999
            best_combo_mode = ""
            best_nb, best_ns = 0, 0
            for mode in ["block", "block+force", "adjust"]:
                for ron_th, roff_th in [(1.0, -1.0), (1.5, -1.5)]:
                    raw = compute_regime_from_indicators(macro.loc[common_idx], list(combo), best_lb, ron_th, roff_th)
                    regimes = apply_confirmation(raw, best_cd)
                    nb, ns, ret, mdd = run_rsi_with_regime_filter(
                        close, rsi_arr_v, bb_arr, regimes, buy_rsi, sell_rsi, rebuy_rsi, mode)
                    if ret > best_combo_ret:
                        best_combo_ret = ret
                        best_combo_mode = mode
                        best_nb, best_ns = nb, ns
            pair_results.append((combo, best_combo_ret, best_combo_mode, best_nb, best_ns))

        pair_results.sort(key=lambda x: x[1], reverse=True)
        for combo, ret, mode, nb, ns in pair_results[:5]:
            vs = ret - ret0
            print(f"    {'+'.join(combo):<20} {ret:>+10,.1f}% (vs RSI {vs:>+10,.1f}%) | {mode} ({nb}B/{ns}S)")

    # ══════════════════════════════════════════════════════════════
    # PART 3: PRACTICAL STRATEGY FOR ALERT BOT
    # ══════════════════════════════════════════════════════════════
    print(f"\n\n{'='*130}")
    print("PART 3: PRACTICAL STRATEGY (simple, robust, alert-ready)")
    print(f"{'='*130}")
    print("Testing simple VIX-only and VIX+Copper filters (most intuitive macro signals)")

    practical_results = []

    # Simple practical filters
    practical_modes = {
        "rsi_only": {"indicators": [], "mode": "none"},
        "vix_block": {"indicators": ["vix"], "mode": "block"},
        "vix_force": {"indicators": ["vix"], "mode": "block+force"},
        "vix_adjust": {"indicators": ["vix"], "mode": "adjust"},
        "copper_block": {"indicators": ["copper"], "mode": "block"},
        "copper_force": {"indicators": ["copper"], "mode": "block+force"},
        "vix+copper_block": {"indicators": ["vix", "copper"], "mode": "block"},
        "vix+copper_force": {"indicators": ["vix", "copper"], "mode": "block+force"},
        "vix+copper_adjust": {"indicators": ["vix", "copper"], "mode": "adjust"},
        "all6_block": {"indicators": available, "mode": "block"},
        "all6_force": {"indicators": available, "mode": "block+force"},
        "all6_adjust": {"indicators": available, "mode": "adjust"},
    }

    for lev_sym, base_sym, buy_rsi, sell_rsi, rebuy_rsi in PAIRS:
        if not os.path.exists(f"data/{lev_sym}.parquet"):
            continue

        lev_df = pd.read_parquet(f"data/{lev_sym}.parquet").sort_index()
        lev_df["rsi14"] = rsi(lev_df["close"], 14)
        lev_df["bb_upper"] = bollinger_upper(lev_df["close"], 20, 2)

        # Test period only (2020+)
        common_idx = macro.index.intersection(lev_df.index).sort_values()
        test_idx = common_idx[common_idx >= SPLIT_DATE]

        close = lev_df.loc[test_idx, "close"].values
        rsi_arr_v = lev_df.loc[test_idx, "rsi14"].values
        bb_arr = lev_df.loc[test_idx, "bb_upper"].values
        bh_ret = run_bh(close)

        print(f"\n[{lev_sym}] Test period (2020+) | B&H: {bh_ret:>+10,.1f}%")
        print(f"  {'Strategy':<22} {'Return%':>10} {'vs B&H':>10} {'MaxDD%':>8} {'B/S':>8}")
        print(f"  {'-'*65}")

        for pname, pconfig in practical_modes.items():
            inds = pconfig["indicators"]
            mode = pconfig["mode"]

            if not inds:
                nb, ns, ret, mdd = run_rsi_with_regime_filter(
                    close, rsi_arr_v, bb_arr, None, buy_rsi, sell_rsi, rebuy_rsi, "none")
            else:
                # Use best practical params: lb=50, threshold depends on # indicators
                if len(inds) == 1:
                    ron_th, roff_th = 0.5, -0.5
                elif len(inds) == 2:
                    ron_th, roff_th = 1.0, -1.0
                else:
                    ron_th, roff_th = 2.0, -2.0
                raw = compute_regime_from_indicators(macro.loc[test_idx], inds, 50, ron_th, roff_th)
                regimes = apply_confirmation(raw, 10)
                nb, ns, ret, mdd = run_rsi_with_regime_filter(
                    close, rsi_arr_v, bb_arr, regimes, buy_rsi, sell_rsi, rebuy_rsi, mode)

            practical_results.append({
                "pair": f"{lev_sym}/{base_sym}", "strategy": pname,
                "n_buys": nb, "n_sells": ns, "return_pct": ret, "max_dd_pct": mdd,
                "bh_pct": bh_ret, "vs_bh": round(ret - bh_ret, 1),
            })
            print(f"  {pname:<22} {ret:>+9,.1f}% {ret - bh_ret:>+9,.1f}% {mdd:>7.1f}% {nb}B/{ns}S")

    # Save all results
    pd.DataFrame(oos_results).to_csv("results/regime_oos_validation.csv", index=False)
    pd.DataFrame(ablation_results).to_csv("results/regime_ablation.csv", index=False)
    pd.DataFrame(practical_results).to_csv("results/regime_practical.csv", index=False)
    print(f"\nSaved: results/regime_oos_validation.csv, regime_ablation.csv, regime_practical.csv")

    # ── Final Summary ──
    print(f"\n\n{'='*130}")
    print("FINAL SUMMARY")
    print(f"{'='*130}")

    print("\n[OOS] Train best → Test performance:")
    for lev_sym, _, _, _, _ in PAIRS:
        pair = f"{lev_sym}/{_}"
        test_best_rows = [r for r in oos_results if r["pair"] == pair and r["period"] == "test_best"]
        test_rsi_rows = [r for r in oos_results if r["pair"] == pair and r["period"] == "train" and r["mode"] == "none"]
        if test_best_rows:
            tb = test_best_rows[0]
            print(f"  {pair}: {tb['return_pct']:>+10,.1f}% ({tb['n_buys']}B/{tb['n_sells']}S) | "
                  f"mode={tb['mode']} lb={tb['lookback']} th={tb['threshold']} cd={tb['confirm']}")

    print("\n[Ablation] Most impactful single indicators (avg vs RSI across pairs):")
    abl_df = pd.DataFrame(ablation_results)
    if not abl_df.empty:
        for ind in available:
            sub = abl_df[abl_df["indicator"] == ind]
            avg_vs = sub["best_vs_rsi"].mean()
            print(f"  {ind:<12} avg vs RSI: {avg_vs:>+10,.1f}%")

    print("\n[Practical] Best simple strategy per pair (test 2020+):")
    prac_df = pd.DataFrame(practical_results)
    for pair, grp in prac_df.groupby("pair"):
        best = grp.loc[grp["return_pct"].idxmax()]
        rsi_row = grp[grp["strategy"] == "rsi_only"].iloc[0]
        print(f"  {pair}: {best['strategy']:<22} {best['return_pct']:>+10,.1f}% ({best['n_buys']}B/{best['n_sells']}S) "
              f"vs RSI {best['return_pct'] - rsi_row['return_pct']:+.1f}% | MaxDD {best['max_dd_pct']:.1f}%")


if __name__ == "__main__":
    main()
