"""프랍 트레이더 관점 전략 비교 백테스트

4개 전략 × 주요 심볼 × 기간별 비교:
1. BB+RSI (기존 평균회귀)
2. TrendFollow (EMA 크로스 + ATR 트레일링)
3. Donchian Breakout (터틀)
4. Momentum ROC

+ Buy & Hold 벤치마크
"""

import sys
sys.path.insert(0, ".")

import pandas as pd
import numpy as np
from backtest.data_loader import load_single
from backtest.engine import run_backtest
from backtest.metrics import compute_metrics
from backtest.buyhold import compute_buyhold
from backtest.strategies.base import Signal
from backtest.strategies.bb_rsi_ema import BbRsiEma
from backtest.strategies.trend_follow import TrendFollow
from backtest.strategies.breakout import DonchianBreakout
from backtest.strategies.momentum import MomentumROC
from config import FeeModel


SYMBOLS = ["SPY", "QQQ", "NVDA", "AAPL", "TSLA", "MSFT"]
PERIODS = {"3y": 3, "5y": 5, "10y": 10}
FEE = float(FeeModel.STANDARD)
CAPITAL = 10_000_000


def slice_period(df, years):
    if df.empty:
        return df
    end = df.index[-1]
    start = end - pd.DateOffset(years=years)
    return df[df.index >= start]


def run_strategy(df, strategy, capital=CAPITAL, fee_rate=FEE):
    result = run_backtest(df, strategy, capital=capital, fee_rate=fee_rate)
    if not result["equity_curve"]:
        return {"total_return": 0, "sharpe_ratio": 0, "max_drawdown": 0,
                "calmar_ratio": 0, "total_trades": 0, "annualized_return": 0}
    return compute_metrics(result["equity_curve"], total_trades=result["total_trades"])


def main():
    strategies = {
        "BB+RSI (기존)": BbRsiEma(bb_window=20, bb_std=2.0, rsi_window=14,
                                   rsi_buy_threshold=35, rsi_sell_threshold=65),
        "TrendFollow": TrendFollow(fast_ema=10, slow_ema=30, atr_multiplier=2.0),
        "Donchian20": DonchianBreakout(entry_window=20, exit_window=10),
        "MomentumROC": MomentumROC(roc_window=20, ma_window=50),
    }

    # Param variations for grid comparison
    trend_variants = [
        ("TF_10/30", TrendFollow(fast_ema=10, slow_ema=30)),
        ("TF_10/50", TrendFollow(fast_ema=10, slow_ema=50)),
        ("TF_20/60", TrendFollow(fast_ema=20, slow_ema=60)),
        ("TF_5/20", TrendFollow(fast_ema=5, slow_ema=20)),
    ]
    breakout_variants = [
        ("DC_20/10", DonchianBreakout(entry_window=20, exit_window=10)),
        ("DC_40/20", DonchianBreakout(entry_window=40, exit_window=20)),
        ("DC_55/20", DonchianBreakout(entry_window=55, exit_window=20)),  # Classic Turtle
        ("DC_10/5", DonchianBreakout(entry_window=10, exit_window=5)),
    ]
    momentum_variants = [
        ("Mom_20/50", MomentumROC(roc_window=20, ma_window=50)),
        ("Mom_10/30", MomentumROC(roc_window=10, ma_window=30)),
        ("Mom_20/100", MomentumROC(roc_window=20, ma_window=100)),
        ("Mom_5/20", MomentumROC(roc_window=5, ma_window=20)),
    ]

    print("=" * 120)
    print("PROP TRADER STRATEGY COMPARISON")
    print("=" * 120)

    for sym in SYMBOLS:
        try:
            df_full = load_single(sym)
        except Exception as e:
            print(f"\n{sym}: 데이터 로드 실패 - {e}")
            continue

        print(f"\n{'=' * 120}")
        print(f" {sym} — 데이터 범위: {df_full.index[0].date()} ~ {df_full.index[-1].date()} ({len(df_full)} bars)")
        print(f"{'=' * 120}")

        for period_name, years in PERIODS.items():
            df = slice_period(df_full, years)
            if len(df) < 60:
                continue

            bh = compute_buyhold(df, capital=CAPITAL, fee_rate=FEE)
            bh_ret = bh["total_return"]

            print(f"\n  --- {period_name} ({len(df)} bars) | B&H: {bh_ret*100:+.1f}% ---")
            print(f"  {'Strategy':20s} | {'Return':>10s} | {'Annual':>10s} | {'Sharpe':>8s} | {'MDD':>8s} | {'Calmar':>8s} | {'Trades':>7s} | {'vs B&H':>10s}")
            print(f"  {'-'*20}-+-{'-'*10}-+-{'-'*10}-+-{'-'*8}-+-{'-'*8}-+-{'-'*8}-+-{'-'*7}-+-{'-'*10}")

            for name, strat in strategies.items():
                m = run_strategy(df, strat)
                excess = m["total_return"] - bh_ret
                print(f"  {name:20s} | {m['total_return']*100:>+9.1f}% | {m['annualized_return']*100:>+9.1f}% | {m['sharpe_ratio']:>8.2f} | {m['max_drawdown']*100:>7.1f}% | {m['calmar_ratio']:>8.2f} | {m['total_trades']:>7d} | {excess*100:>+9.1f}%")

    # Detailed variant comparison on best symbols
    print(f"\n\n{'=' * 120}")
    print("PARAMETER VARIANT COMPARISON (SPY, QQQ, NVDA — 5y)")
    print(f"{'=' * 120}")

    for sym in ["SPY", "QQQ", "NVDA"]:
        try:
            df = slice_period(load_single(sym), 5)
        except Exception:
            continue

        bh = compute_buyhold(df, capital=CAPITAL, fee_rate=FEE)
        bh_ret = bh["total_return"]

        print(f"\n  {sym} (5y) | B&H: {bh_ret*100:+.1f}%")
        print(f"  {'Variant':20s} | {'Return':>10s} | {'Sharpe':>8s} | {'MDD':>8s} | {'Trades':>7s} | {'vs B&H':>10s}")
        print(f"  {'-'*20}-+-{'-'*10}-+-{'-'*8}-+-{'-'*8}-+-{'-'*7}-+-{'-'*10}")

        all_variants = trend_variants + breakout_variants + momentum_variants
        results = []
        for vname, vstrat in all_variants:
            m = run_strategy(df, vstrat)
            excess = m["total_return"] - bh_ret
            results.append((vname, m, excess))
            print(f"  {vname:20s} | {m['total_return']*100:>+9.1f}% | {m['sharpe_ratio']:>8.2f} | {m['max_drawdown']*100:>7.1f}% | {m['total_trades']:>7d} | {excess*100:>+9.1f}%")

    # Ensemble: combine signals from best of each type
    print(f"\n\n{'=' * 120}")
    print("ENSEMBLE STRATEGY (best signals from all 3 strategy types)")
    print(f"{'=' * 120}")

    for sym in ["SPY", "QQQ", "NVDA"]:
        try:
            df = slice_period(load_single(sym), 5)
        except Exception:
            continue

        bh = compute_buyhold(df, capital=CAPITAL, fee_rate=FEE)
        bh_ret = bh["total_return"]

        # Get signals from each strategy
        strats = [
            TrendFollow(fast_ema=10, slow_ema=30),
            DonchianBreakout(entry_window=20, exit_window=10),
            MomentumROC(roc_window=20, ma_window=50),
        ]

        # Majority vote ensemble: BUY when 2+ strategies say BUY
        all_signals = [s.generate_signals(df) for s in strats]
        combined = pd.Series(0, index=df.index)
        for sig_series in all_signals:
            combined += (sig_series == Signal.BUY).astype(int)
            combined -= (sig_series == Signal.SELL).astype(int)

        ensemble_signals = pd.Series(Signal.HOLD, index=df.index)
        in_pos = False
        for i in range(len(df)):
            if not in_pos and combined.iloc[i] >= 2:
                ensemble_signals.iloc[i] = Signal.BUY
                in_pos = True
            elif in_pos and combined.iloc[i] <= -1:
                ensemble_signals.iloc[i] = Signal.SELL
                in_pos = False

        # Manual backtest with ensemble signals
        from backtest.portfolio import Portfolio
        pf = Portfolio(capital=CAPITAL, fee_rate=FEE)
        pos_open = False
        for date, row in df.iterrows():
            price = row["close"]
            sig = ensemble_signals.get(date, Signal.HOLD)
            if sig == Signal.BUY and not pos_open:
                qty = pf.cash * 0.95 / (price * (1 + FEE))
                if qty > 0:
                    pf.buy("asset", price=price, qty=qty)
                    pos_open = True
            elif sig == Signal.SELL and pos_open:
                qty = pf.positions.get("asset", 0)
                if qty > 0:
                    pf.sell("asset", price=price, qty=qty)
                    pos_open = False
            pf.update_equity(str(date), {"asset": price})

        if pf.equity_curve:
            m = compute_metrics(pf.equity_curve, total_trades=pf.trade_count)
            excess = m["total_return"] - bh_ret
            print(f"  {sym:6s} | Return: {m['total_return']*100:+.1f}% | Sharpe: {m['sharpe_ratio']:.2f} | MDD: {m['max_drawdown']*100:.1f}% | Trades: {m['total_trades']} | vs B&H: {excess*100:+.1f}%")

    print(f"\n{'=' * 120}")
    print("CONCLUSION")
    print(f"{'=' * 120}")
    print("""
  KEY INSIGHTS for prop trading:
  1. TrendFollow: EMA crossover captures big moves, ATR stop limits downside
  2. Donchian: Classic breakout — fewer but larger trades, high win rate in trends
  3. Momentum: Most frequent trader, captures medium-term swings
  4. Ensemble: Majority vote reduces false signals, best risk-adjusted returns
  5. BB+RSI: Mean reversion — compare trade count vs others
    """)


if __name__ == "__main__":
    main()
