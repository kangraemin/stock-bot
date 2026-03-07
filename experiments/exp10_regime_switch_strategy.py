"""
실험 10: Regime-Based Strategy Switching
- 고변동/약세 → 평균회귀(BB+RSI), 저변동/강세 → 추세추종
- VIX 수준 + SPY SMA200으로 레짐 판별
"""
import pandas as pd
import numpy as np
import os
import sys
sys.path.insert(0, os.path.dirname(__file__))

from backtest.strategies.bb_rsi_ema import BbRsiEma
from backtest.strategies.trend_follow import TrendFollow
from backtest.strategies.base import Signal
from backtest.engine import run_backtest
from backtest.metrics import compute_metrics

TOTAL_CASH = 10000.0
FEE_RATE = 0.0025

SYMBOLS = ["SOXL", "TQQQ", "SPXL", "TNA"]
VIX_THRESHOLDS = [20, 25, 30]
SMA_PERIODS = [100, 200]


def load_spy_regime(sma_period):
    """SPY SMA 기반 강세/약세"""
    spy_path = "data/SPY.parquet"
    if not os.path.exists(spy_path):
        return None
    spy = pd.read_parquet(spy_path).sort_index()
    spy["sma"] = spy["close"].rolling(sma_period).mean()
    spy["bull"] = spy["close"] > spy["sma"]
    return spy["bull"]


def load_vix():
    vix_path = "data/^VIX.parquet"
    if not os.path.exists(vix_path):
        return None
    return pd.read_parquet(vix_path).sort_index()["close"]


def run_regime_switch(df, vix_series, bull_series, vix_thresh):
    """레짐 스위칭: bull+low_vix → trend, else → mean_reversion"""
    n = len(df)
    cash = TOTAL_CASH
    shares = 0.0
    state = 0  # 0=cash, 1=holding
    current_strategy = None
    n_buys = 0; n_sells = 0; n_switches = 0
    peak_val = TOTAL_CASH; max_dd = 0.0

    close = df["close"].values

    # Pre-compute signals for both strategies
    mr_strategy = BbRsiEma()  # mean reversion (default params)
    tf_strategy = TrendFollow()  # trend follow (default params)

    mr_signals = mr_strategy.generate_signals(df)
    tf_signals = tf_strategy.generate_signals(df)

    for i in range(n):
        date = df.index[i]
        price = close[i]

        # Determine regime
        is_bull = bull_series.get(date, True) if bull_series is not None else True
        vix_val = vix_series.get(date, 20) if vix_series is not None else 20
        is_low_vol = vix_val < vix_thresh

        # Choose strategy
        if is_bull and is_low_vol:
            target_strategy = "trend"
            signal = tf_signals.iloc[i] if i < len(tf_signals) else Signal.HOLD
        else:
            target_strategy = "mean_reversion"
            signal = mr_signals.iloc[i] if i < len(mr_signals) else Signal.HOLD

        # Strategy switch → force close position
        if current_strategy is not None and target_strategy != current_strategy:
            if shares > 0:
                cash += shares * price * (1 - FEE_RATE)
                shares = 0; n_sells += 1; state = 0
            n_switches += 1
        current_strategy = target_strategy

        # Execute signal
        if state == 0 and signal == Signal.BUY:
            shares = cash * (1 - FEE_RATE) / price
            cash = 0; n_buys += 1; state = 1
        elif state == 1 and signal == Signal.SELL:
            cash = shares * price * (1 - FEE_RATE)
            shares = 0; n_sells += 1; state = 0

        val = cash + shares * price
        if val > peak_val: peak_val = val
        dd = (val - peak_val) / peak_val
        if dd < max_dd: max_dd = dd

    final = cash + shares * close[-1]
    ret = (final / TOTAL_CASH - 1) * 100
    return n_buys, n_sells, n_switches, round(ret, 1), round(max_dd * 100, 1)


def run_single_strategy(df, strategy_name):
    """단일 전략 벤치마크"""
    if strategy_name == "mean_reversion":
        strategy = BbRsiEma()
    else:
        strategy = TrendFollow()

    result = run_backtest(df, strategy, capital=TOTAL_CASH, fee_rate=FEE_RATE)
    metrics = compute_metrics(result["equity_curve"], result["total_trades"])
    return (result["total_trades"] // 2, result["total_trades"] - result["total_trades"] // 2,
            round(metrics["total_return"] * 100, 1), round(metrics["max_drawdown"] * 100, 1))


def run_bh(close):
    shares = TOTAL_CASH * (1 - FEE_RATE) / close[0]
    return round((shares * close[-1] / TOTAL_CASH - 1) * 100, 1)


def main():
    print("=" * 120)
    print("EXP 10: REGIME-BASED STRATEGY SWITCHING")
    print("=" * 120)

    vix_series = load_vix()
    if vix_series is None:
        print("  VIX data not found!")
        return

    all_results = []

    for sym in SYMBOLS:
        path = f"data/{sym}.parquet"
        if not os.path.exists(path):
            continue

        df = pd.read_parquet(path).sort_index()
        close = df["close"].values
        bh_ret = run_bh(close)

        # Single strategy baselines
        mr_b, mr_s, mr_ret, mr_dd = run_single_strategy(df, "mean_reversion")
        tf_b, tf_s, tf_ret, tf_dd = run_single_strategy(df, "trend_follow")

        print(f"\n[{sym}] {len(df)} bars | B&H: {bh_ret:+.1f}%")
        print(f"  MeanRev only: {mr_ret:>+10,.1f}% ({mr_b}B/{mr_s}S, MaxDD {mr_dd}%)")
        print(f"  TrendF only:  {tf_ret:>+10,.1f}% ({tf_b}B/{tf_s}S, MaxDD {tf_dd}%)")

        best_ret = -999; best_row = None

        for sma_p in SMA_PERIODS:
            bull_series = load_spy_regime(sma_p)

            for vt in VIX_THRESHOLDS:
                nb, ns, nsw, ret, mdd = run_regime_switch(
                    df, vix_series, bull_series, vt)

                row = {
                    "symbol": sym, "sma_period": sma_p, "vix_threshold": vt,
                    "n_buys": nb, "n_sells": ns, "n_switches": nsw,
                    "return_pct": ret, "max_dd_pct": mdd,
                    "mr_pct": mr_ret, "mr_dd": mr_dd,
                    "tf_pct": tf_ret, "tf_dd": tf_dd,
                    "bh_pct": bh_ret,
                    "vs_mr": round(ret - mr_ret, 1),
                    "vs_tf": round(ret - tf_ret, 1),
                    "vs_bh": round(ret - bh_ret, 1),
                }
                all_results.append(row)

                if ret > best_ret:
                    best_ret = ret; best_row = row

        if best_row:
            print(f"  Best switch: {best_ret:>+10,.1f}% | SMA{best_row['sma_period']} "
                  f"VIX<{best_row['vix_threshold']} ({best_row['n_buys']}B/{best_row['n_sells']}S, "
                  f"{best_row['n_switches']} switches, MaxDD {best_row['max_dd_pct']}%)")
            print(f"  vs MR: {best_row['vs_mr']:+.1f}% | vs TF: {best_row['vs_tf']:+.1f}%")

    res_df = pd.DataFrame(all_results)
    res_df.to_csv("results/exp10_regime_switch.csv", index=False)
    print(f"\nSaved: results/exp10_regime_switch.csv ({len(all_results)} rows)")


if __name__ == "__main__":
    main()
