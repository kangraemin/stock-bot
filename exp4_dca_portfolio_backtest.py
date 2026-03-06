"""
실험 4: DCA 포트폴리오 최적화
- 매월 $500 적립 시 7종목 비중 최적화
- 균등, 레버리지 중심, 인덱스 중심, 변동성 역비례 등 비교
"""
import pandas as pd
import numpy as np
import os, time

MONTHLY_INVEST = 500.0
FEE_RATE = 0.0025

SYMBOLS = ["SOXL", "TQQQ", "SPXL", "TNA", "QLD", "UWM", "QQQ"]

# 포트폴리오 전략
PORTFOLIOS = {
    "equal": {s: 1/7 for s in SYMBOLS},
    "3x_heavy": {"SOXL": 0.25, "TQQQ": 0.25, "SPXL": 0.15, "TNA": 0.10, "QLD": 0.10, "UWM": 0.05, "QQQ": 0.10},
    "index_heavy": {"SOXL": 0.05, "TQQQ": 0.05, "SPXL": 0.05, "TNA": 0.05, "QLD": 0.15, "UWM": 0.10, "QQQ": 0.55},
    "nasdaq_focus": {"SOXL": 0.15, "TQQQ": 0.35, "SPXL": 0.0, "TNA": 0.0, "QLD": 0.20, "UWM": 0.0, "QQQ": 0.30},
    "broad_lev": {"SOXL": 0.20, "TQQQ": 0.20, "SPXL": 0.20, "TNA": 0.10, "QLD": 0.10, "UWM": 0.10, "QQQ": 0.10},
    "barbell": {"SOXL": 0.20, "TQQQ": 0.20, "SPXL": 0.0, "TNA": 0.0, "QLD": 0.0, "UWM": 0.0, "QQQ": 0.60},
    "soxl_only": {"SOXL": 1.0, "TQQQ": 0, "SPXL": 0, "TNA": 0, "QLD": 0, "UWM": 0, "QQQ": 0},
    "tqqq_only": {"SOXL": 0, "TQQQ": 1.0, "SPXL": 0, "TNA": 0, "QLD": 0, "UWM": 0, "QQQ": 0},
    "qqq_only": {"SOXL": 0, "TQQQ": 0, "SPXL": 0, "TNA": 0, "QLD": 0, "UWM": 0, "QQQ": 1.0},
}


def run_dca_portfolio(all_close, weights, monthly_invest=MONTHLY_INVEST):
    """
    all_close: dict of symbol → close array (aligned index)
    weights: dict of symbol → weight
    """
    # Find common length
    n = min(len(v) for v in all_close.values())
    months = pd.Series(range(n)).apply(lambda i: i // 21)  # ~21 trading days per month

    holdings = {s: 0.0 for s in all_close}
    total_invested = 0.0
    peak_val = 0.0
    max_dd = 0.0
    prev_month = -1

    for i in range(n):
        cur_month = months.iloc[i]
        if cur_month != prev_month:
            prev_month = cur_month
            # Monthly DCA
            for sym, w in weights.items():
                if w <= 0: continue
                amount = monthly_invest * w
                price = all_close[sym][i]
                if price > 0:
                    shares = amount * (1 - FEE_RATE) / price
                    holdings[sym] += shares
                    total_invested += amount

        # Portfolio value
        val = sum(holdings[s] * all_close[s][i] for s in holdings)
        if val > peak_val: peak_val = val
        if peak_val > 0:
            dd = (val - peak_val) / peak_val
            if dd < max_dd: max_dd = dd

    final_val = sum(holdings[s] * all_close[s][-1] for s in holdings)
    ret = (final_val / total_invested - 1) * 100 if total_invested > 0 else 0
    n_months = int(months.iloc[-1]) + 1
    return {
        "total_invested": round(total_invested, 2),
        "final_value": round(final_val, 2),
        "return_pct": round(ret, 1),
        "max_dd_pct": round(max_dd * 100, 1),
        "n_months": n_months,
    }


def run_dca_portfolio_rsi_boost(all_close, all_rsi, weights, monthly_invest=MONTHLY_INVEST,
                                 boost_rsi=45, boost_mult=2.0):
    """DCA + RSI 부스트: RSI < boost_rsi면 해당 종목 매수액 * boost_mult"""
    n = min(len(v) for v in all_close.values())
    months = pd.Series(range(n)).apply(lambda i: i // 21)

    holdings = {s: 0.0 for s in all_close}
    total_invested = 0.0
    peak_val = 0.0; max_dd = 0.0
    prev_month = -1

    for i in range(n):
        cur_month = months.iloc[i]
        if cur_month != prev_month:
            prev_month = cur_month
            for sym, w in weights.items():
                if w <= 0: continue
                rv = all_rsi[sym][i] if not np.isnan(all_rsi[sym][i]) else 50
                mult = boost_mult if rv < boost_rsi else 1.0
                amount = monthly_invest * w * mult
                price = all_close[sym][i]
                if price > 0:
                    shares = amount * (1 - FEE_RATE) / price
                    holdings[sym] += shares
                    total_invested += amount

        val = sum(holdings[s] * all_close[s][i] for s in holdings)
        if val > peak_val: peak_val = val
        if peak_val > 0:
            dd = (val - peak_val) / peak_val
            if dd < max_dd: max_dd = dd

    final_val = sum(holdings[s] * all_close[s][-1] for s in holdings)
    ret = (final_val / total_invested - 1) * 100 if total_invested > 0 else 0
    n_months = int(months.iloc[-1]) + 1
    return {
        "total_invested": round(total_invested, 2),
        "final_value": round(final_val, 2),
        "return_pct": round(ret, 1),
        "max_dd_pct": round(max_dd * 100, 1),
        "n_months": n_months,
    }


def rsi_func(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def main():
    print("=" * 120)
    print("EXP 4: DCA PORTFOLIO OPTIMIZATION")
    print("=" * 120)

    # Load data
    dfs = {}
    for sym in SYMBOLS:
        path = f"data/{sym}.parquet"
        if not os.path.exists(path):
            print(f"  SKIP {sym}")
            continue
        dfs[sym] = pd.read_parquet(path).sort_index()

    available = [s for s in SYMBOLS if s in dfs]
    print(f"Available: {available}")

    # Common index
    common_idx = dfs[available[0]].index
    for sym in available[1:]:
        common_idx = common_idx.intersection(dfs[sym].index)
    common_idx = common_idx.sort_values()
    print(f"Common bars: {len(common_idx)} ({common_idx[0].strftime('%Y-%m-%d')} ~ {common_idx[-1].strftime('%Y-%m-%d')})")

    all_close = {s: dfs[s].loc[common_idx, "close"].values for s in available}
    all_rsi = {s: rsi_func(dfs[s].loc[common_idx, "close"], 14).values for s in available}

    all_results = []

    # Basic DCA portfolios
    print(f"\n{'='*100}")
    print("DCA PORTFOLIO COMPARISON (no RSI boost)")
    print(f"{'='*100}")
    print(f"{'Portfolio':<16} {'Invested':>12} {'Final':>14} {'Return%':>10} {'MaxDD%':>8}")
    print("-" * 70)

    for pname, weights in PORTFOLIOS.items():
        # Filter to available symbols
        w = {s: weights.get(s, 0) for s in available}
        total_w = sum(w.values())
        if total_w <= 0: continue
        w = {s: v/total_w for s, v in w.items()}  # normalize

        result = run_dca_portfolio(all_close, w)
        result["portfolio"] = pname
        result["boost"] = "none"
        all_results.append(result)
        print(f"{pname:<16} ${result['total_invested']:>11,.0f} ${result['final_value']:>13,.0f} "
              f"{result['return_pct']:>+9.1f}% {result['max_dd_pct']:>7.1f}%")

    # DCA + RSI boost
    print(f"\n{'='*100}")
    print("DCA + RSI BOOST (boost_rsi=45, mult=2x)")
    print(f"{'='*100}")
    print(f"{'Portfolio':<16} {'Invested':>12} {'Final':>14} {'Return%':>10} {'MaxDD%':>8}")
    print("-" * 70)

    for pname, weights in PORTFOLIOS.items():
        w = {s: weights.get(s, 0) for s in available}
        total_w = sum(w.values())
        if total_w <= 0: continue
        w = {s: v/total_w for s, v in w.items()}

        result = run_dca_portfolio_rsi_boost(all_close, all_rsi, w, boost_rsi=45, boost_mult=2.0)
        result["portfolio"] = pname
        result["boost"] = "rsi45_2x"
        all_results.append(result)
        print(f"{pname:<16} ${result['total_invested']:>11,.0f} ${result['final_value']:>13,.0f} "
              f"{result['return_pct']:>+9.1f}% {result['max_dd_pct']:>7.1f}%")

    # Grid: boost params
    print(f"\n{'='*100}")
    print("RSI BOOST GRID (equal portfolio)")
    print(f"{'='*100}")
    w_equal = {s: 1/len(available) for s in available}
    boost_rsis = [30, 35, 40, 45, 50]
    boost_mults = [1.5, 2.0, 3.0, 5.0]

    base_result = run_dca_portfolio(all_close, w_equal)
    print(f"Baseline (no boost): {base_result['return_pct']:>+.1f}%")

    for br in boost_rsis:
        for bm in boost_mults:
            result = run_dca_portfolio_rsi_boost(all_close, all_rsi, w_equal, boost_rsi=br, boost_mult=bm)
            result["portfolio"] = "equal"
            result["boost"] = f"rsi{br}_{bm}x"
            result["boost_rsi"] = br
            result["boost_mult"] = bm
            all_results.append(result)

    # Print best boost params
    boost_results = [r for r in all_results if "boost_rsi" in r]
    if boost_results:
        best_boost = max(boost_results, key=lambda r: r["return_pct"])
        print(f"Best boost: rsi<{best_boost['boost_rsi']} x{best_boost['boost_mult']} → "
              f"{best_boost['return_pct']:>+.1f}% (invested ${best_boost['total_invested']:,.0f})")

    pd.DataFrame(all_results).to_csv("results/exp4_dca_portfolio.csv", index=False)
    print(f"\nSaved: results/exp4_dca_portfolio.csv")


if __name__ == "__main__":
    main()
