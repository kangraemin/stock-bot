"""
실험 12: Strategy Benchmark
- 5개 전략 동일 조건 비교
- bb_rsi_ema, trend_follow, breakout, momentum, adaptive_trend
- 전 기간, $10,000, 0.25% 수수료
"""
import pandas as pd
import numpy as np
import os
import sys
sys.path.insert(0, os.path.dirname(__file__))

from backtest.strategies.bb_rsi_ema import BbRsiEma
from backtest.strategies.trend_follow import TrendFollow
from backtest.strategies.breakout import DonchianBreakout
from backtest.strategies.momentum import MomentumROC
from backtest.strategies.adaptive_trend import AdaptiveTrend
from backtest.engine import run_backtest
from backtest.metrics import compute_metrics

TOTAL_CASH = 10000.0
FEE_RATE = 0.0025

SYMBOLS = ["SOXL", "TQQQ", "SPXL", "TNA"]

STRATEGIES = {
    "BB+RSI+EMA": BbRsiEma,
    "TrendFollow": TrendFollow,
    "Breakout": DonchianBreakout,
    "Momentum": MomentumROC,
    "AdaptiveTrend": AdaptiveTrend,
}


def run_bh(close):
    shares = TOTAL_CASH * (1 - FEE_RATE) / close[0]
    return round((shares * close[-1] / TOTAL_CASH - 1) * 100, 1)


def main():
    print("=" * 120)
    print("EXP 12: STRATEGY BENCHMARK (5 Strategies × 4 Symbols)")
    print("=" * 120)

    all_results = []

    for sym in SYMBOLS:
        path = f"data/{sym}.parquet"
        if not os.path.exists(path):
            continue

        df = pd.read_parquet(path).sort_index()
        bh_ret = run_bh(df["close"].values)

        print(f"\n{'='*80}")
        print(f"[{sym}] {len(df)} bars | B&H: {bh_ret:+.1f}%")
        print(f"{'='*80}")
        print(f"  {'Strategy':20s} {'Return':>12s} {'MaxDD':>10s} {'Sharpe':>8s} {'Calmar':>8s} {'Trades':>8s} {'vs B&H':>10s}")
        print(f"  {'-'*78}")

        for strat_name, strat_class in STRATEGIES.items():
            try:
                strategy = strat_class()
                result = run_backtest(df, strategy, capital=TOTAL_CASH, fee_rate=FEE_RATE)
                metrics = compute_metrics(result["equity_curve"], result["total_trades"])

                ret = round(metrics["total_return"] * 100, 1)
                mdd = round(metrics["max_drawdown"] * 100, 1)
                sharpe = round(metrics.get("sharpe_ratio", 0), 2)
                calmar = round(metrics.get("calmar_ratio", 0), 2)
                trades = result["total_trades"]
                n_buys = trades // 2 + trades % 2
                n_sells = trades // 2

                row = {
                    "symbol": sym, "strategy": strat_name,
                    "return_pct": ret, "max_dd_pct": mdd,
                    "sharpe": sharpe, "calmar": calmar,
                    "total_trades": trades, "n_buys": n_buys, "n_sells": n_sells,
                    "bh_pct": bh_ret,
                    "vs_bh": round(ret - bh_ret, 1),
                }
                all_results.append(row)

                print(f"  {strat_name:20s} {ret:>+11,.1f}% {mdd:>9,.1f}% {sharpe:>8.2f} {calmar:>8.2f} "
                      f"{n_buys}B/{n_sells}S {ret-bh_ret:>+9,.1f}%")

            except Exception as e:
                print(f"  {strat_name:20s} ERROR: {e}")
                all_results.append({
                    "symbol": sym, "strategy": strat_name,
                    "return_pct": 0, "max_dd_pct": 0,
                    "sharpe": 0, "calmar": 0,
                    "total_trades": 0, "n_buys": 0, "n_sells": 0,
                    "bh_pct": bh_ret, "vs_bh": -bh_ret,
                    "error": str(e),
                })

    # Summary table
    if all_results:
        print(f"\n{'='*120}")
        print("STRATEGY RANKING (by avg return across symbols)")
        print(f"{'='*120}")

        res_df = pd.DataFrame(all_results)
        summary = res_df.groupby("strategy").agg({
            "return_pct": "mean",
            "max_dd_pct": "mean",
            "sharpe": "mean",
            "total_trades": "mean",
            "vs_bh": "mean",
        }).sort_values("return_pct", ascending=False)

        print(f"  {'Strategy':20s} {'Avg Return':>12s} {'Avg MaxDD':>12s} {'Avg Sharpe':>12s} {'Avg Trades':>12s} {'Avg vs B&H':>12s}")
        print(f"  {'-'*80}")
        for strat, row in summary.iterrows():
            print(f"  {strat:20s} {row['return_pct']:>+11,.1f}% {row['max_dd_pct']:>11,.1f}% "
                  f"{row['sharpe']:>11.2f} {row['total_trades']:>11.0f} {row['vs_bh']:>+11,.1f}%")

        res_df.to_csv("results/exp12_strategy_benchmark.csv", index=False)
        print(f"\nSaved: results/exp12_strategy_benchmark.csv ({len(all_results)} rows)")


if __name__ == "__main__":
    main()
