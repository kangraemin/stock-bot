"""
Leveraged Bull Backtest
========================
TQQQ 기본 보유 + SPY 실현변동성 기반 포지션 사이징
- Vol < 15%:  TQQQ 100%
- Vol 15-25%: TQQQ 60% + QQQ 40%
- Vol 25-35%: QQQ 80% + Cash 20%
- Vol > 35%:  QQQ 50% + Cash 50%
- 주간 체크, 변동성 구간 변경 시에만 리밸런싱
- Cash에 연 4% 무위험 수익 가산
- 수수료 0.25%
"""

import numpy as np
import pandas as pd
from backtest.data_loader import load_single

# ── Config ──
FEE = 0.0025
RISK_FREE_RATE = 0.04
INITIAL_CAPITAL = 10000

VOL_ALLOCATIONS = {
    "ultra_low":  {"TQQQ": 1.00},                          # vol < 15%
    "low":        {"TQQQ": 0.60, "QQQ": 0.40},             # 15% <= vol < 25%
    "high":       {"QQQ": 0.80, "Cash": 0.20},             # 25% <= vol < 35%
    "extreme":    {"QQQ": 0.50, "Cash": 0.50},             # vol >= 35%
}

VOL_THRESHOLDS = [0.15, 0.25, 0.35]

PERIODS = {
    "3y": 252 * 3,
    "5y": 252 * 5,
    "10y": 252 * 10,
    "Full": None,
}


def get_vol_regime(spy_close: pd.Series, idx: int) -> str:
    if idx < 21:
        return "ultra_low"
    returns_21d = spy_close.iloc[idx - 21:idx].pct_change().dropna()
    realized_vol = returns_21d.std() * np.sqrt(252)
    if realized_vol < VOL_THRESHOLDS[0]:
        return "ultra_low"
    elif realized_vol < VOL_THRESHOLDS[1]:
        return "low"
    elif realized_vol < VOL_THRESHOLDS[2]:
        return "high"
    else:
        return "extreme"


def run_leveraged_bull(data: dict[str, pd.DataFrame], period_days: int | None = None):
    common_idx = data["SPY"].index
    for sym in ["QQQ", "TQQQ"]:
        common_idx = common_idx.intersection(data[sym].index)
    common_idx = common_idx.sort_values()

    if period_days is not None:
        common_idx = common_idx[-period_days:]

    spy_close = data["SPY"].loc[common_idx, "close"]
    qqq_close = data["QQQ"].loc[common_idx, "close"]
    tqqq_close = data["TQQQ"].loc[common_idx, "close"]

    closes = {"SPY": spy_close, "QQQ": qqq_close, "TQQQ": tqqq_close}

    cash = INITIAL_CAPITAL
    holdings = {}
    cash_holding = 0.0
    current_regime = None
    portfolio_values = []
    regime_log = []
    rebalance_count = 0
    last_rebalance_week = None

    for i in range(len(common_idx)):
        date = common_idx[i]
        week_key = (date.isocalendar()[0], date.isocalendar()[1])

        # Current portfolio value
        port_value = cash
        for sym, shares in holdings.items():
            port_value += shares * closes[sym].iloc[i]
        daily_rf = (1 + RISK_FREE_RATE) ** (1 / 252) - 1
        cash_holding *= (1 + daily_rf)
        port_value += cash_holding

        # Weekly vol check — only rebalance on regime change
        if week_key != last_rebalance_week:
            regime = get_vol_regime(spy_close, i)
            if regime != current_regime:
                # Liquidate
                total_cash = cash
                for sym, shares in holdings.items():
                    total_cash += shares * closes[sym].iloc[i] * (1 - FEE)
                total_cash += cash_holding
                cash_holding = 0.0
                holdings = {}

                # Allocate
                alloc = VOL_ALLOCATIONS[regime]
                for sym, weight in alloc.items():
                    amount = total_cash * weight
                    if sym == "Cash":
                        cash_holding += amount
                    else:
                        cost_after_fee = amount * (1 - FEE)
                        shares = cost_after_fee / closes[sym].iloc[i]
                        holdings[sym] = shares

                cash = 0.0
                current_regime = regime
                rebalance_count += 1
                regime_log.append((date, regime))

                # Recalculate after rebalance
                port_value = cash
                for sym, shares in holdings.items():
                    port_value += shares * closes[sym].iloc[i]
                port_value += cash_holding

            last_rebalance_week = week_key

        portfolio_values.append(port_value)

    equity = pd.Series(portfolio_values, index=common_idx, name="LeveragedBull")
    return equity, regime_log, rebalance_count


def compute_metrics(equity: pd.Series, label: str) -> dict:
    returns = equity.pct_change().dropna()
    total_return = (equity.iloc[-1] / equity.iloc[0]) - 1
    days = (equity.index[-1] - equity.index[0]).days
    years = days / 365.25
    ann_return = (1 + total_return) ** (1 / years) - 1 if years > 0 else 0
    ann_vol = returns.std() * np.sqrt(252)
    sharpe = (ann_return - RISK_FREE_RATE) / ann_vol if ann_vol > 0 else 0

    drawdown = equity / equity.cummax() - 1
    mdd = drawdown.min()
    calmar = ann_return / abs(mdd) if mdd != 0 else 0

    # Recovery days
    peak_idx = equity.cummax()
    in_dd = equity < peak_idx
    if in_dd.any():
        dd_groups = (~in_dd).cumsum()
        dd_lengths = in_dd.groupby(dd_groups).sum()
        max_recovery = int(dd_lengths.max()) if len(dd_lengths) > 0 else 0
    else:
        max_recovery = 0

    return {
        "Strategy": label,
        "Total Return": f"{total_return:.1%}",
        "Annualized": f"{ann_return:.1%}",
        "Sharpe": f"{sharpe:.2f}",
        "MDD": f"{mdd:.1%}",
        "Calmar": f"{calmar:.2f}",
        "Max Recovery (days)": max_recovery,
    }


def buy_and_hold(data: pd.DataFrame, common_idx: pd.DatetimeIndex) -> pd.Series:
    close = data.loc[common_idx, "close"]
    return close / close.iloc[0] * INITIAL_CAPITAL


def main():
    print("Loading data...")
    data = {}
    for sym in ["SPY", "QQQ", "TQQQ"]:
        data[sym] = load_single(sym)

    tqqq_start = data["TQQQ"].index[0]
    for sym in data:
        data[sym] = data[sym][data[sym].index >= tqqq_start]

    print(f"Data range: {tqqq_start.date()} ~ {data['SPY'].index[-1].date()}")
    print(f"TQQQ inception: {tqqq_start.date()}\n")

    all_results = []

    for period_name, period_days in PERIODS.items():
        print(f"{'='*60}")
        print(f"  Period: {period_name}")
        print(f"{'='*60}")

        equity, regime_log, rebalance_count = run_leveraged_bull(data, period_days)
        common_idx = equity.index

        results = [compute_metrics(equity, "Leveraged Bull")]
        for sym in ["SPY", "QQQ", "TQQQ"]:
            bh_equity = buy_and_hold(data[sym], common_idx)
            results.append(compute_metrics(bh_equity, f"{sym} B&H"))

        df = pd.DataFrame(results)
        print(df.to_string(index=False))
        print(f"\nRebalance count: {rebalance_count}")

        if regime_log:
            regimes = pd.DataFrame(regime_log, columns=["Date", "Regime"])
            regime_counts = regimes["Regime"].value_counts()
            print(f"\nVol regime transitions:")
            for r, c in regime_counts.items():
                print(f"  {r:10s}: {c:3d} times")

        print()
        all_results.append((period_name, results, regime_log))

    # Summary
    print("=" * 60)
    print("  LEVERAGED BULL THESIS")
    print("=" * 60)
    full_results = all_results[-1][1]
    lb = full_results[0]
    tqqq = full_results[3]
    qqq = full_results[2]
    print(f"Leveraged Bull:  {lb['Annualized']} ann. | Sharpe {lb['Sharpe']} | MDD {lb['MDD']} | Calmar {lb['Calmar']}")
    print(f"TQQQ B&H:        {tqqq['Annualized']} ann. | Sharpe {tqqq['Sharpe']} | MDD {tqqq['MDD']} | Calmar {tqqq['Calmar']}")
    print(f"QQQ B&H:          {qqq['Annualized']} ann. | Sharpe {qqq['Sharpe']} | MDD {qqq['MDD']} | Calmar {qqq['Calmar']}")
    print(f"\nKey insight: Stay in the market ALWAYS. Vol-size your leverage, never go full cash.")

    return all_results


if __name__ == "__main__":
    results = main()
