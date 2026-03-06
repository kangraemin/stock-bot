"""
매크로 레짐 + RSI 타이밍 결합 백테스트
- 레짐: Risk-On / Neutral / Risk-Off (매크로 지표 기반)
- 매수/매도: RSI 기반 (기존 검증된 전략)
- 레짐이 필터 역할: Risk-Off면 매수 차단 or 포지션 축소

추가 실험: 확인 기간 (confirmation) - N일 연속 레짐 유지 시에만 전환
"""
import pandas as pd
import numpy as np
import os
import time

TOTAL_CASH = 10000.0
FEE_RATE = 0.0025

MACRO_SYMBOLS = {
    "copper": "HG=F",
    "oil": "CL=F",
    "vix": "^VIX",
    "gold": "GC=F",
    "tnx": "^TNX",
    "dollar": "DX-Y.NYB",
}

PAIRS = [
    ("SOXL", "SOXX", 25, 60, 55),   # buy_rsi, sell_rsi, rebuy_rsi (grid search 최적값)
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
    macro = pd.DataFrame(frames).sort_index().ffill()
    return macro


def compute_regime_scores(macro, lookback=50):
    signals = pd.DataFrame(index=macro.index)

    if "copper" in macro.columns:
        sma = macro["copper"].rolling(lookback).mean()
        signals["copper"] = np.where(macro["copper"] > sma, 1, -1)

    if "oil" in macro.columns:
        oil_ret = macro["oil"].pct_change(lookback)
        signals["oil"] = np.where(oil_ret < -0.15, -1, np.where(oil_ret > 0.1, 0.5, 0))

    if "vix" in macro.columns:
        sma = macro["vix"].rolling(lookback).mean()
        signals["vix"] = np.where(macro["vix"] < sma * 0.9, 1,
                          np.where(macro["vix"] > sma * 1.1, -1, 0))
        signals["vix_ext"] = np.where(macro["vix"] > 30, -1, 0)

    if "gold" in macro.columns:
        gold_ret = macro["gold"].pct_change(lookback)
        signals["gold"] = np.where(gold_ret > 0.1, -0.5, np.where(gold_ret < -0.05, 0.5, 0))

    if "tnx" in macro.columns:
        tnx_chg = macro["tnx"].diff(lookback)
        signals["tnx"] = np.where(tnx_chg > 0.5, -1, np.where(tnx_chg < -0.3, 0.5, 0))

    if "dollar" in macro.columns:
        sma = macro["dollar"].rolling(lookback).mean()
        signals["dollar"] = np.where(macro["dollar"] > sma * 1.02, -1,
                             np.where(macro["dollar"] < sma * 0.98, 1, 0))

    return signals.sum(axis=1).values


def apply_confirmation(raw_regimes, confirm_days):
    """N일 연속 동일 레짐이어야 전환"""
    if confirm_days <= 1:
        return raw_regimes

    n = len(raw_regimes)
    confirmed = [raw_regimes[0]] * n
    streak = 1
    prev_raw = raw_regimes[0]
    current_confirmed = raw_regimes[0]

    for i in range(1, n):
        if raw_regimes[i] == prev_raw:
            streak += 1
        else:
            streak = 1
            prev_raw = raw_regimes[i]

        if streak >= confirm_days:
            current_confirmed = raw_regimes[i]

        confirmed[i] = current_confirmed

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


# ── Strategy 1: Regime as Filter ──
def run_regime_filter(close, rsi_arr, bb_upper, regimes,
                      buy_rsi, sell_rsi, rebuy_rsi, filter_mode):
    """
    filter_mode:
      0 = "block": Risk-Off에서 매수 차단 (매도는 허용)
      1 = "half": Risk-Off에서 절반만 매수
      2 = "force_sell": Risk-Off 전환 시 강제 매도
      3 = "block+force": Risk-Off에서 매수차단 + 강제매도
    """
    n = len(close)
    cash = TOTAL_CASH
    shares = 0.0
    state = 0  # 0=CASH, 1=HOLDING, 2=WAIT_REBUY
    n_buys = 0
    n_sells = 0
    peak_val = TOTAL_CASH
    max_dd = 0.0

    for i in range(n):
        price = close[i]
        rv = rsi_arr[i]
        bb = bb_upper[i]
        regime = regimes[i]

        if np.isnan(rv) or np.isnan(bb):
            val = cash + shares * price
            if val > peak_val: peak_val = val
            continue

        # Force sell on Risk-Off
        if filter_mode in (2, 3) and regime == "RISK_OFF" and state == 1:
            cash = shares * price * (1 - FEE_RATE)
            shares = 0
            n_sells += 1
            state = 2

        if state == 0:
            if rv < buy_rsi:
                if regime == "RISK_OFF" and filter_mode in (0, 3):
                    pass  # blocked
                elif regime == "RISK_OFF" and filter_mode == 1:
                    buy_amt = cash * 0.5
                    shares = buy_amt * (1 - FEE_RATE) / price
                    cash -= buy_amt
                    n_buys += 1
                    state = 1
                else:
                    shares = cash * (1 - FEE_RATE) / price
                    cash = 0
                    n_buys += 1
                    state = 1

        elif state == 1:
            if rv > sell_rsi and price > bb:
                cash = shares * price * (1 - FEE_RATE)
                shares = 0
                n_sells += 1
                state = 2

        elif state == 2:
            if rv < rebuy_rsi:
                if regime == "RISK_OFF" and filter_mode in (0, 3):
                    pass  # blocked
                elif regime == "RISK_OFF" and filter_mode == 1:
                    buy_amt = cash * 0.5
                    shares = buy_amt * (1 - FEE_RATE) / price
                    cash -= buy_amt
                    n_buys += 1
                    state = 1
                else:
                    shares = cash * (1 - FEE_RATE) / price
                    cash = 0
                    n_buys += 1
                    state = 1

        val = cash + shares * price
        if val > peak_val: peak_val = val
        dd = (val - peak_val) / peak_val
        if dd < max_dd: max_dd = dd

    final = cash + shares * close[-1]
    ret = (final / TOTAL_CASH - 1) * 100
    return n_buys, n_sells, round(final, 2), round(ret, 1), round(max_dd * 100, 1)


# ── Strategy 2: Regime-adjusted RSI thresholds ──
def run_regime_adjusted_rsi(close, rsi_arr, bb_upper, regimes,
                            buy_rsi, sell_rsi, rebuy_rsi, adjust_mode):
    """
    adjust_mode:
      0 = Risk-On: 매수RSI+10 (더 공격적), Risk-Off: 매수RSI-10 (더 보수적)
      1 = Risk-On: 매도RSI+10 (더 오래 보유), Risk-Off: 매도RSI-10 (빨리 매도)
      2 = 둘 다 조정
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
        regime = regimes[i]

        if np.isnan(rv) or np.isnan(bb):
            val = cash + shares * price
            if val > peak_val: peak_val = val
            continue

        # Adjust thresholds based on regime
        if regime == "RISK_ON":
            adj_buy = buy_rsi + (10 if adjust_mode in (0, 2) else 0)
            adj_sell = sell_rsi + (10 if adjust_mode in (1, 2) else 0)
            adj_rebuy = rebuy_rsi + (10 if adjust_mode in (0, 2) else 0)
        elif regime == "RISK_OFF":
            adj_buy = buy_rsi - (10 if adjust_mode in (0, 2) else 0)
            adj_sell = sell_rsi - (10 if adjust_mode in (1, 2) else 0)
            adj_rebuy = rebuy_rsi - (10 if adjust_mode in (0, 2) else 0)
        else:
            adj_buy = buy_rsi
            adj_sell = sell_rsi
            adj_rebuy = rebuy_rsi

        adj_buy = max(5, min(adj_buy, 50))
        adj_sell = max(50, min(adj_sell, 90))
        adj_rebuy = max(10, min(adj_rebuy, 70))

        if state == 0:
            if rv < adj_buy:
                shares = cash * (1 - FEE_RATE) / price
                cash = 0
                n_buys += 1
                state = 1

        elif state == 1:
            if rv > adj_sell and price > bb:
                cash = shares * price * (1 - FEE_RATE)
                shares = 0
                n_sells += 1
                state = 2

        elif state == 2:
            if rv < adj_rebuy:
                shares = cash * (1 - FEE_RATE) / price
                cash = 0
                n_buys += 1
                state = 1

        val = cash + shares * price
        if val > peak_val: peak_val = val
        dd = (val - peak_val) / peak_val
        if dd < max_dd: max_dd = dd

    final = cash + shares * close[-1]
    ret = (final / TOTAL_CASH - 1) * 100
    return n_buys, n_sells, round(final, 2), round(ret, 1), round(max_dd * 100, 1)


def run_baseline_rsi(close, rsi_arr, bb_upper, buy_rsi, sell_rsi, rebuy_rsi):
    """기본 RSI 전략 (레짐 없이)"""
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
    return n_buys, n_sells, round(final, 2), round(ret, 1), round(max_dd * 100, 1)


def run_bh(close):
    shares = TOTAL_CASH * (1 - FEE_RATE) / close[0]
    final = shares * close[-1]
    return round((final / TOTAL_CASH - 1) * 100, 1)


def main():
    print("=" * 130)
    print("MACRO REGIME + RSI TIMING COMBINED BACKTEST")
    print("=" * 130)

    macro = load_macro()
    print(f"Macro data: {len(macro)} rows, {macro.index[0]} ~ {macro.index[-1]}")

    lookbacks = [20, 50, 100]
    thresholds = [(1.0, -1.0), (1.5, -1.5), (2.0, -2.0), (2.5, -2.5)]
    confirm_days_list = [1, 3, 5, 10, 20]  # 1 = no confirmation
    filter_modes = {0: "block", 1: "half", 2: "force_sell", 3: "block+force"}
    adjust_modes = {0: "buy_adj", 1: "sell_adj", 2: "both_adj"}

    os.makedirs("results", exist_ok=True)
    all_results = []
    start = time.time()

    for lev_sym, base_sym, buy_rsi_opt, sell_rsi_opt, rebuy_rsi_opt in PAIRS:
        if not os.path.exists(f"data/{lev_sym}.parquet"):
            print(f"  SKIP {lev_sym}: data not found")
            continue

        print(f"\n{'='*80}")
        print(f"[{lev_sym}/{base_sym}] buy_rsi={buy_rsi_opt} sell_rsi={sell_rsi_opt} rebuy_rsi={rebuy_rsi_opt}")
        print(f"{'='*80}")

        lev_df = pd.read_parquet(f"data/{lev_sym}.parquet").sort_index()
        lev_df["rsi14"] = rsi(lev_df["close"], 14)
        lev_df["bb_upper"] = bollinger_upper(lev_df["close"], 20, 2)

        common_idx = macro.index.intersection(lev_df.index).sort_values()
        close = lev_df.loc[common_idx, "close"].values
        rsi_arr = lev_df.loc[common_idx, "rsi14"].values
        bb_arr = lev_df.loc[common_idx, "bb_upper"].values

        bh_ret = run_bh(close)
        nb, ns, _, rsi_ret, rsi_dd = run_baseline_rsi(close, rsi_arr, bb_arr,
                                                        buy_rsi_opt, sell_rsi_opt, rebuy_rsi_opt)
        print(f"  B&H: {bh_ret:>+10,.1f}%")
        print(f"  RSI only: {rsi_ret:>+10,.1f}% (MaxDD {rsi_dd}%, {nb}B/{ns}S)")
        print(f"  Bars: {len(common_idx)}")

        best_ret = -999
        best_row = None

        for lookback in lookbacks:
            scores = compute_regime_scores(macro.loc[common_idx], lookback=lookback)

            for ron_th, roff_th in thresholds:
                raw_regimes = []
                for s in scores:
                    if np.isnan(s):
                        raw_regimes.append("NEUTRAL")
                    elif s >= ron_th:
                        raw_regimes.append("RISK_ON")
                    elif s <= roff_th:
                        raw_regimes.append("RISK_OFF")
                    else:
                        raw_regimes.append("NEUTRAL")

                for confirm_days in confirm_days_list:
                    regimes = apply_confirmation(raw_regimes, confirm_days)
                    n_roff = sum(1 for r in regimes if r == "RISK_OFF")
                    pct_roff = round(n_roff / len(regimes) * 100, 1)

                    # Strategy 1: Filter modes
                    for fm, fm_name in filter_modes.items():
                        nb, ns, fv, ret, mdd = run_regime_filter(
                            close, rsi_arr, bb_arr, regimes,
                            buy_rsi_opt, sell_rsi_opt, rebuy_rsi_opt, fm)

                        row = {
                            "lev_symbol": lev_sym, "base_symbol": base_sym,
                            "strategy": f"filter_{fm_name}",
                            "lookback": lookback,
                            "threshold": f"{ron_th}/{roff_th}",
                            "confirm_days": confirm_days,
                            "n_buys": nb, "n_sells": ns,
                            "return_pct": ret, "max_dd_pct": mdd,
                            "bh_pct": bh_ret, "rsi_only_pct": rsi_ret,
                            "vs_bh": round(ret - bh_ret, 1),
                            "vs_rsi": round(ret - rsi_ret, 1),
                            "pct_risk_off": pct_roff,
                        }
                        all_results.append(row)
                        if ret > best_ret:
                            best_ret = ret
                            best_row = row

                    # Strategy 2: Adjusted RSI thresholds
                    for am, am_name in adjust_modes.items():
                        nb, ns, fv, ret, mdd = run_regime_adjusted_rsi(
                            close, rsi_arr, bb_arr, regimes,
                            buy_rsi_opt, sell_rsi_opt, rebuy_rsi_opt, am)

                        row = {
                            "lev_symbol": lev_sym, "base_symbol": base_sym,
                            "strategy": f"adjust_{am_name}",
                            "lookback": lookback,
                            "threshold": f"{ron_th}/{roff_th}",
                            "confirm_days": confirm_days,
                            "n_buys": nb, "n_sells": ns,
                            "return_pct": ret, "max_dd_pct": mdd,
                            "bh_pct": bh_ret, "rsi_only_pct": rsi_ret,
                            "vs_bh": round(ret - bh_ret, 1),
                            "vs_rsi": round(ret - rsi_ret, 1),
                            "pct_risk_off": pct_roff,
                        }
                        all_results.append(row)
                        if ret > best_ret:
                            best_ret = ret
                            best_row = row

        print(f"  BEST: {best_ret:>+10,.1f}% | {best_row['strategy']} | "
              f"lb={best_row['lookback']} th={best_row['threshold']} confirm={best_row['confirm_days']}d | "
              f"{best_row['n_buys']}B/{best_row['n_sells']}S | MaxDD={best_row['max_dd_pct']}% | "
              f"vs B&H: {best_row['vs_bh']:+.1f}% | vs RSI: {best_row['vs_rsi']:+.1f}%")

    elapsed = time.time() - start
    print(f"\nTotal: {len(all_results):,} results in {elapsed:.1f}s")

    res_df = pd.DataFrame(all_results)
    res_df.to_csv("results/regime_rsi_combined_grid.csv", index=False)
    print(f"Saved: results/regime_rsi_combined_grid.csv")

    # ── Summary tables ──
    print(f"\n{'='*140}")
    print("BEST PER PAIR × STRATEGY TYPE")
    print(f"{'='*140}")
    print(f"{'Pair':<12} {'Strategy':<20} {'LB':>4} {'Thresh':<8} {'Conf':>5} "
          f"{'B/S':>6} {'Return%':>10} {'B&H%':>10} {'RSI%':>10} {'vs B&H':>10} {'vs RSI':>10} {'MaxDD%':>7} {'%ROff':>6}")
    print("-" * 140)

    for (lev, base), grp in res_df.groupby(["lev_symbol", "base_symbol"]):
        # Group by strategy type
        strat_types = sorted(grp["strategy"].unique())
        for strat in strat_types:
            sub = grp[grp["strategy"] == strat]
            best = sub.loc[sub["return_pct"].idxmax()]
            pair = f"{lev}/{base}"
            print(f"{pair:<12} {strat:<20} {best['lookback']:>4} {best['threshold']:<8} {best['confirm_days']:>5} "
                  f"{best['n_buys']}/{best['n_sells']:>3} {best['return_pct']:>9,.1f}% {best['bh_pct']:>9,.1f}% {best['rsi_only_pct']:>9,.1f}% "
                  f"{best['vs_bh']:>+9,.1f}% {best['vs_rsi']:>+9,.1f}% {best['max_dd_pct']:>6.1f}% {best['pct_risk_off']:>5.1f}%")
        print()

    # ── Confirmation period impact ──
    print(f"\n{'='*100}")
    print("CONFIRMATION PERIOD IMPACT (best per confirm_days, averaged across pairs)")
    print(f"{'='*100}")
    for cd in confirm_days_list:
        sub = res_df[res_df["confirm_days"] == cd]
        # best per pair
        bests = sub.loc[sub.groupby("lev_symbol")["return_pct"].idxmax()]
        avg_vs_rsi = bests["vs_rsi"].mean()
        avg_dd = bests["max_dd_pct"].mean()
        avg_rebal = (bests["n_buys"] + bests["n_sells"]).mean()
        print(f"  confirm={cd:>2}d | avg vs RSI: {avg_vs_rsi:>+8.1f}% | avg MaxDD: {avg_dd:>6.1f}% | avg trades: {avg_rebal:>5.1f}")

    # ── Does regime improve RSI? ──
    print(f"\n{'='*80}")
    print("DOES MACRO REGIME IMPROVE RSI STRATEGY?")
    print(f"{'='*80}")
    for (lev, base), grp in res_df.groupby(["lev_symbol", "base_symbol"]):
        beat_rsi = len(grp[grp["vs_rsi"] > 0])
        beat_bh = len(grp[grp["vs_bh"] > 0])
        total = len(grp)
        best = grp.loc[grp["return_pct"].idxmax()]
        print(f"  {lev}/{base}: beat RSI {beat_rsi}/{total} ({beat_rsi/total*100:.0f}%) | "
              f"beat B&H {beat_bh}/{total} ({beat_bh/total*100:.0f}%) | "
              f"best vs RSI: {best['vs_rsi']:+.1f}% ({best['strategy']})")


if __name__ == "__main__":
    main()
