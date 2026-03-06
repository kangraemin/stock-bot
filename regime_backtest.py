"""
매크로 레짐 감지 백테스트
- 구리(HG=F), 유가(CL=F), VIX(^VIX), 금(GC=F), 10Y금리(^TNX), 달러(DX-Y.NYB)
- 레짐: Risk-On / Neutral / Risk-Off
- 레짐별 포지션: 3x 풀 / 1x or 절반 / 현금
- 레버리지 ETF 4쌍 (SOXL/SOXX, TQQQ/QQQ, SPXL/SPY, TNA/IWM)
"""
import pandas as pd
import numpy as np
import os
import time

TOTAL_CASH = 10000.0
FEE_RATE = 0.0025

# ── Macro data loading ──
MACRO_SYMBOLS = {
    "copper": "HG=F",
    "oil": "CL=F",
    "vix": "^VIX",
    "gold": "GC=F",
    "tnx": "^TNX",
    "dollar": "DX-Y.NYB",
}

PAIRS = [
    ("SOXL", "SOXX"),
    ("TQQQ", "QQQ"),
    ("SPXL", "SPY"),
    ("TNA", "IWM"),
]


def load_macro():
    """매크로 지표 로드 + 레짐 시그널 계산"""
    frames = {}
    for name, sym in MACRO_SYMBOLS.items():
        path = f"data/{sym}.parquet"
        if not os.path.exists(path):
            print(f"  WARN: {path} not found, skipping {name}")
            continue
        df = pd.read_parquet(path)
        df = df.sort_index()
        frames[name] = df["close"]

    macro = pd.DataFrame(frames)
    macro = macro.sort_index()
    macro = macro.ffill()  # forward fill gaps (different trading days for futures)
    return macro


def compute_regime_signals(macro, lookback=50):
    """
    각 매크로 지표의 트렌드를 계산하고 레짐 스코어를 산출

    Risk-On 신호:
      - 구리 상승 (경기 확장)
      - VIX 하락 (공포 감소)
      - 달러 하락 (리스크온 환경)
      - 금리 안정/하락 (유동성 개선)

    Risk-Off 신호:
      - 구리 하락
      - VIX 상승
      - 금 급등 (안전자산 선호)
      - 달러 상승

    각 지표를 SMA 대비 위치로 z-score화 → 합산 → 레짐 판정
    """
    signals = pd.DataFrame(index=macro.index)

    # 구리: SMA 위 = risk-on (+1), 아래 = risk-off (-1)
    if "copper" in macro.columns:
        sma = macro["copper"].rolling(lookback).mean()
        signals["copper_trend"] = np.where(macro["copper"] > sma, 1, -1)

    # 유가: 급락 = risk-off, 안정/상승 = neutral/risk-on
    if "oil" in macro.columns:
        oil_ret = macro["oil"].pct_change(lookback)
        signals["oil_trend"] = np.where(oil_ret < -0.15, -1, np.where(oil_ret > 0.1, 0.5, 0))

    # VIX: 낮으면 risk-on, 높으면 risk-off
    if "vix" in macro.columns:
        sma = macro["vix"].rolling(lookback).mean()
        # VIX 역방향: VIX가 SMA 위 = risk-off
        signals["vix_trend"] = np.where(macro["vix"] < sma * 0.9, 1,
                                np.where(macro["vix"] > sma * 1.1, -1, 0))
        # VIX > 30 = 강한 risk-off
        signals["vix_extreme"] = np.where(macro["vix"] > 30, -1, 0)

    # 금: 급등 = risk-off (안전자산 선호)
    if "gold" in macro.columns:
        gold_ret = macro["gold"].pct_change(lookback)
        signals["gold_trend"] = np.where(gold_ret > 0.1, -0.5, np.where(gold_ret < -0.05, 0.5, 0))

    # 10Y 금리: 급등 = risk-off (긴축), 안정 = neutral
    if "tnx" in macro.columns:
        tnx_chg = macro["tnx"].diff(lookback)
        signals["tnx_trend"] = np.where(tnx_chg > 0.5, -1, np.where(tnx_chg < -0.3, 0.5, 0))

    # 달러: 강세 = risk-off, 약세 = risk-on
    if "dollar" in macro.columns:
        sma = macro["dollar"].rolling(lookback).mean()
        signals["dollar_trend"] = np.where(macro["dollar"] > sma * 1.02, -1,
                                   np.where(macro["dollar"] < sma * 0.98, 1, 0))

    # 합산 스코어
    signals["score"] = signals.sum(axis=1)

    return signals


def regime_from_score(score, risk_on_thresh, risk_off_thresh):
    """스코어 → 레짐 매핑"""
    if score >= risk_on_thresh:
        return "RISK_ON"
    elif score <= risk_off_thresh:
        return "RISK_OFF"
    else:
        return "NEUTRAL"


def load_pair(lev_sym, base_sym):
    """레버리지 + 기초자산 데이터 로드"""
    lev = pd.read_parquet(f"data/{lev_sym}.parquet").sort_index()
    base = pd.read_parquet(f"data/{base_sym}.parquet").sort_index()
    return lev, base


def run_regime_backtest(lev_close, base_close, regimes,
                        risk_on_alloc, neutral_alloc, risk_off_alloc):
    """
    레짐 기반 백테스트
    - risk_on_alloc: (lev_pct, base_pct, cash_pct) e.g. (1.0, 0, 0) = 100% 3x
    - neutral_alloc: e.g. (0, 1.0, 0) = 100% base
    - risk_off_alloc: e.g. (0, 0, 1.0) = 100% cash
    """
    n = len(lev_close)
    cash = TOTAL_CASH
    lev_shares = 0.0
    base_shares = 0.0
    n_rebal = 0
    peak_val = TOTAL_CASH
    max_dd = 0.0
    prev_regime = None

    for i in range(n):
        regime = regimes[i]
        lp = lev_close[i]
        bp = base_close[i]

        if np.isnan(lp) or np.isnan(bp):
            continue

        # Rebalance on regime change
        if regime != prev_regime:
            # Liquidate
            val = cash + lev_shares * lp + base_shares * bp
            cash = val
            lev_shares = 0.0
            base_shares = 0.0

            # Allocate
            if regime == "RISK_ON":
                alloc = risk_on_alloc
            elif regime == "NEUTRAL":
                alloc = neutral_alloc
            else:
                alloc = risk_off_alloc

            lev_amt = cash * alloc[0]
            base_amt = cash * alloc[1]
            # rest stays cash

            if lev_amt > 1:
                lev_shares = lev_amt * (1 - FEE_RATE) / lp
            if base_amt > 1:
                base_shares = base_amt * (1 - FEE_RATE) / bp
            cash -= (lev_amt + base_amt)
            if regime != prev_regime and prev_regime is not None:
                n_rebal += 1
            prev_regime = regime

        val = cash + lev_shares * lp + base_shares * bp
        if val > peak_val:
            peak_val = val
        dd = (val - peak_val) / peak_val
        if dd < max_dd:
            max_dd = dd

    final = cash + lev_shares * lev_close[-1] + base_shares * base_close[-1]
    ret = (final / TOTAL_CASH - 1) * 100
    return {
        "n_rebalances": n_rebal,
        "final_value": round(final, 2),
        "return_pct": round(ret, 1),
        "max_dd_pct": round(max_dd * 100, 1),
    }


def run_bh(close):
    shares = TOTAL_CASH * (1 - FEE_RATE) / close[0]
    final = shares * close[-1]
    return round((final / TOTAL_CASH - 1) * 100, 1)


# ── Allocation strategies ──
# (lev_pct, base_pct, cash_pct)
ALLOC_STRATEGIES = {
    "aggressive": {
        "risk_on": (1.0, 0, 0),      # 100% 3x
        "neutral": (0.5, 0.5, 0),    # 50% 3x + 50% base
        "risk_off": (0, 0, 1.0),     # 100% cash
    },
    "balanced": {
        "risk_on": (0.7, 0.3, 0),    # 70% 3x + 30% base
        "neutral": (0, 1.0, 0),      # 100% base
        "risk_off": (0, 0, 1.0),     # 100% cash
    },
    "conservative": {
        "risk_on": (0.5, 0.5, 0),    # 50% 3x + 50% base
        "neutral": (0, 0.5, 0.5),    # 50% base + 50% cash
        "risk_off": (0, 0, 1.0),     # 100% cash
    },
    "lev_rotation": {
        "risk_on": (1.0, 0, 0),      # 100% 3x
        "neutral": (0, 1.0, 0),      # 100% base
        "risk_off": (0, 0, 1.0),     # 100% cash
    },
    "base_only": {
        "risk_on": (0, 1.0, 0),      # 100% base (no leverage)
        "neutral": (0, 0.5, 0.5),    # 50% base + 50% cash
        "risk_off": (0, 0, 1.0),     # 100% cash
    },
}


def main():
    print("=" * 120)
    print("MACRO REGIME DETECTION BACKTEST")
    print("=" * 120)

    # Load macro data
    print("\n[1] Loading macro data...")
    macro = load_macro()
    print(f"  Macro data: {len(macro)} rows, {macro.columns.tolist()}")
    print(f"  Date range: {macro.index[0]} ~ {macro.index[-1]}")

    # Grid: lookback × thresholds
    lookbacks = [20, 50, 100]
    thresholds = [
        (1.0, -1.0),   # tight
        (1.5, -1.5),   # medium
        (2.0, -2.0),   # wide
        (2.5, -2.5),   # very wide
    ]

    os.makedirs("results", exist_ok=True)
    all_results = []
    start = time.time()

    for lev_sym, base_sym in PAIRS:
        if not os.path.exists(f"data/{lev_sym}.parquet") or not os.path.exists(f"data/{base_sym}.parquet"):
            print(f"  SKIP {lev_sym}/{base_sym}: data not found")
            continue

        print(f"\n[{lev_sym}/{base_sym}]")
        lev_df, base_df = load_pair(lev_sym, base_sym)

        # Align all data
        common_idx = macro.index.intersection(lev_df.index).intersection(base_df.index)
        common_idx = common_idx.sort_values()

        lev_close = lev_df.loc[common_idx, "close"].values
        base_close = base_df.loc[common_idx, "close"].values

        bh_lev = run_bh(lev_close)
        bh_base = run_bh(base_close)
        print(f"  B&H {lev_sym}: {bh_lev:>+10,.1f}%  |  B&H {base_sym}: {bh_base:>+10,.1f}%")
        print(f"  Common bars: {len(common_idx)} ({common_idx[0].strftime('%Y-%m-%d')} ~ {common_idx[-1].strftime('%Y-%m-%d')})")

        best_ret = -999
        best_row = None

        for lookback in lookbacks:
            signals = compute_regime_signals(macro.loc[common_idx], lookback=lookback)
            scores = signals["score"].values

            for ron_th, roff_th in thresholds:
                regimes = [regime_from_score(s, ron_th, roff_th) for s in scores]
                n_risk_on = sum(1 for r in regimes if r == "RISK_ON")
                n_neutral = sum(1 for r in regimes if r == "NEUTRAL")
                n_risk_off = sum(1 for r in regimes if r == "RISK_OFF")

                for strat_name, allocs in ALLOC_STRATEGIES.items():
                    result = run_regime_backtest(
                        lev_close, base_close, regimes,
                        allocs["risk_on"], allocs["neutral"], allocs["risk_off"],
                    )
                    result.update({
                        "lev_symbol": lev_sym,
                        "base_symbol": base_sym,
                        "lookback": lookback,
                        "risk_on_thresh": ron_th,
                        "risk_off_thresh": roff_th,
                        "strategy": strat_name,
                        "bh_lev_pct": bh_lev,
                        "bh_base_pct": bh_base,
                        "vs_bh_lev": round(result["return_pct"] - bh_lev, 1),
                        "vs_bh_base": round(result["return_pct"] - bh_base, 1),
                        "pct_risk_on": round(n_risk_on / len(regimes) * 100, 1),
                        "pct_neutral": round(n_neutral / len(regimes) * 100, 1),
                        "pct_risk_off": round(n_risk_off / len(regimes) * 100, 1),
                    })
                    all_results.append(result)

                    if result["return_pct"] > best_ret:
                        best_ret = result["return_pct"]
                        best_row = result

        print(f"  Best: {best_ret:>+10,.1f}% | {best_row['strategy']} | "
              f"lb={best_row['lookback']} th={best_row['risk_on_thresh']}/{best_row['risk_off_thresh']} | "
              f"rebal={best_row['n_rebalances']} | MaxDD={best_row['max_dd_pct']:.1f}% | "
              f"vs B&H({lev_sym}): {best_row['vs_bh_lev']:+.1f}%")

    elapsed = time.time() - start
    print(f"\nTotal: {len(all_results):,} results in {elapsed:.1f}s")

    # Save CSV
    res_df = pd.DataFrame(all_results)
    res_df.to_csv("results/macro_regime_grid.csv", index=False)
    print(f"Saved: results/macro_regime_grid.csv")

    # ── Summary ──
    print(f"\n{'='*140}")
    print("BEST PER PAIR × STRATEGY")
    print(f"{'='*140}")
    print(f"{'Pair':<12} {'Strategy':<14} {'LB':>4} {'ROn':>5} {'ROff':>5} "
          f"{'Rebal':>6} {'Return%':>10} {'B&H Lev%':>10} {'B&H Base%':>10} "
          f"{'vs Lev':>10} {'vs Base':>10} {'MaxDD%':>7} "
          f"{'%RiskOn':>8} {'%Neut':>6} {'%RiskOff':>8}")
    print("-" * 140)

    for (lev, base), grp in res_df.groupby(["lev_symbol", "base_symbol"]):
        for strat in ALLOC_STRATEGIES:
            sub = grp[grp["strategy"] == strat]
            if sub.empty:
                continue
            best = sub.loc[sub["return_pct"].idxmax()]
            pair = f"{lev}/{base}"
            print(f"{pair:<12} {strat:<14} {best['lookback']:>4} {best['risk_on_thresh']:>5.1f} {best['risk_off_thresh']:>5.1f} "
                  f"{best['n_rebalances']:>6} {best['return_pct']:>9,.1f}% {best['bh_lev_pct']:>9,.1f}% {best['bh_base_pct']:>9,.1f}% "
                  f"{best['vs_bh_lev']:>+9,.1f}% {best['vs_bh_base']:>+9,.1f}% {best['max_dd_pct']:>6.1f}% "
                  f"{best['pct_risk_on']:>7.1f}% {best['pct_neutral']:>5.1f}% {best['pct_risk_off']:>7.1f}%")
        print()

    # ── Risk-adjusted: best Sharpe-like (return / |MaxDD|) ──
    print(f"\n{'='*120}")
    print("BEST RISK-ADJUSTED (Return / |MaxDD|) PER PAIR")
    print(f"{'='*120}")
    res_df["risk_adj"] = res_df["return_pct"] / res_df["max_dd_pct"].abs().clip(lower=1)
    for (lev, base), grp in res_df.groupby(["lev_symbol", "base_symbol"]):
        best = grp.loc[grp["risk_adj"].idxmax()]
        pair = f"{lev}/{base}"
        print(f"  {pair:<12} {best['strategy']:<14} lb={best['lookback']:>3} "
              f"ret={best['return_pct']:>+10,.1f}% MaxDD={best['max_dd_pct']:>6.1f}% "
              f"risk_adj={best['risk_adj']:.2f} rebal={best['n_rebalances']}")

    # ── Does macro regime beat B&H? ──
    print(f"\n{'='*80}")
    print("DOES MACRO REGIME BEAT B&H?")
    print(f"{'='*80}")
    for (lev, base), grp in res_df.groupby(["lev_symbol", "base_symbol"]):
        beat_lev = len(grp[grp["vs_bh_lev"] > 0])
        beat_base = len(grp[grp["vs_bh_base"] > 0])
        total = len(grp)
        print(f"  {lev}/{base}: beat B&H({lev}) {beat_lev}/{total} ({beat_lev/total*100:.0f}%) | "
              f"beat B&H({base}) {beat_base}/{total} ({beat_base/total*100:.0f}%)")


if __name__ == "__main__":
    main()
