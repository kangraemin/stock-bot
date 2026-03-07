"""
Defensive Bear Backtest
========================
Dual Momentum + Volatility Targeting
- Monthly rebalance only (minimize whipsaw)
- Relative momentum: QQQ vs SPY (6-month return)
- Position sizing via volatility targeting:
  - Target: 12% annual volatility
  - Scale = target_vol / realized_vol (21-day, annualized)
  - Capped at 100% (no leverage)
  - Remainder in cash (earning risk-free)
- When momentum is negative (both negative) → 100% cash
- Fee: 0.25% per trade

Key insight: vol targeting naturally reduces exposure during crashes.
No lagging SMA, no whipsaw. Vol spikes → position shrinks automatically.
"""

import numpy as np
import pandas as pd
from backtest.data_loader import load_single

FEE = 0.0025
RISK_FREE_RATE = 0.04
INITIAL_CAPITAL = 10000
MOM_LOOKBACK = 126       # 6 months
VOL_LOOKBACK = 21        # 1 month realized vol
TARGET_VOL = 0.115       # 11.5% target annual vol → MDD ~-20%
MAX_EXPOSURE = 1.0       # no leverage

PERIODS = {
    "3y": 252 * 3,
    "5y": 252 * 5,
    "10y": 252 * 10,
    "Full": None,
}


def run_defensive_backtest(data: dict[str, pd.DataFrame], period_days: int | None = None):
    common_idx = data["SPY"].index.intersection(data["QQQ"].index).sort_values()
    if period_days is not None:
        common_idx = common_idx[-period_days:]

    spy_close = data["SPY"].loc[common_idx, "close"]
    qqq_close = data["QQQ"].loc[common_idx, "close"]
    closes = {"SPY": spy_close, "QQQ": qqq_close}

    # Precompute daily returns for vol calculation
    spy_rets = spy_close.pct_change()
    qqq_rets = qqq_close.pct_change()

    cash = INITIAL_CAPITAL
    holdings = {}
    cash_holding = 0.0
    current_month = None
    portfolio_values = []
    signal_log = []
    rebalance_count = 0
    daily_rf = (1 + RISK_FREE_RATE) ** (1 / 252) - 1

    min_start = max(MOM_LOOKBACK, VOL_LOOKBACK + 1)

    for i in range(len(common_idx)):
        date = common_idx[i]
        month_key = (date.year, date.month)

        cash_holding *= (1 + daily_rf)

        port_value = cash
        for sym, shares in holdings.items():
            port_value += shares * closes[sym].iloc[i]
        port_value += cash_holding

        if i < min_start:
            if month_key != current_month:
                current_month = month_key
            portfolio_values.append(port_value)
            continue

        # Monthly rebalance
        if month_key != current_month:
            # Momentum signals
            spy_mom = spy_close.iloc[i] / spy_close.iloc[i - MOM_LOOKBACK] - 1
            qqq_mom = qqq_close.iloc[i] / qqq_close.iloc[i - MOM_LOOKBACK] - 1

            # Both negative → cash
            if spy_mom <= 0 and qqq_mom <= 0:
                if holdings:
                    total = cash
                    for sym, shares in holdings.items():
                        total += shares * closes[sym].iloc[i] * (1 - FEE)
                    total += cash_holding
                    cash = 0.0
                    cash_holding = total
                    holdings = {}
                    rebalance_count += 1
                signal_log.append((date, "CASH", 0.0))
                current_month = month_key
                port_value = cash + cash_holding
                portfolio_values.append(port_value)
                continue

            # Pick winner
            if qqq_mom >= spy_mom:
                winner, loser = "QQQ", "SPY"
            else:
                winner, loser = "SPY", "QQQ"

            # Compute blended portfolio vol (70/30 weighted)
            w_rets = qqq_rets if winner == "QQQ" else spy_rets
            l_rets = spy_rets if winner == "QQQ" else qqq_rets
            blend_rets = 0.70 * w_rets.iloc[i - VOL_LOOKBACK:i] + 0.30 * l_rets.iloc[i - VOL_LOOKBACK:i]
            realized_vol = blend_rets.std() * np.sqrt(252)

            if realized_vol <= 0:
                realized_vol = TARGET_VOL

            # Scale exposure
            exposure = min(TARGET_VOL / realized_vol, MAX_EXPOSURE)

            # Liquidate
            total = cash
            for sym, shares in holdings.items():
                total += shares * closes[sym].iloc[i] * (1 - FEE)
            total += cash_holding
            cash = 0.0
            cash_holding = 0.0
            holdings = {}

            # Allocate: exposure * (70% winner + 30% loser) + rest in cash
            invest_amount = total * exposure
            cash_holding = total * (1 - exposure)

            for sym, weight in [(winner, 0.70), (loser, 0.30)]:
                amount = invest_amount * weight
                cost = amount * (1 - FEE)
                holdings[sym] = cost / closes[sym].iloc[i]

            rebalance_count += 1
            signal_log.append((date, f"{winner} {exposure:.0%}", exposure))

            # Recalculate
            port_value = cash
            for sym, shares in holdings.items():
                port_value += shares * closes[sym].iloc[i]
            port_value += cash_holding

            current_month = month_key

        portfolio_values.append(port_value)

    equity = pd.Series(portfolio_values, index=common_idx, name="DefensiveBear")
    return equity, signal_log, rebalance_count


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

    peak = equity.cummax()
    in_dd = equity < peak
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
        "Recovery (days)": max_recovery,
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
    print()

    all_results = []

    for period_name, period_days in PERIODS.items():
        print(f"{'='*60}")
        print(f"  Period: {period_name}")
        print(f"{'='*60}")

        equity, signal_log, rebalance_count = run_defensive_backtest(data, period_days)
        common_idx = equity.index

        results = [compute_metrics(equity, "Defensive Bear")]
        for sym in ["SPY", "QQQ", "TQQQ"]:
            bh_equity = buy_and_hold(data[sym], common_idx)
            results.append(compute_metrics(bh_equity, f"{sym} B&H"))

        df = pd.DataFrame(results)
        print(df.to_string(index=False))
        print(f"\nRebalance count: {rebalance_count}")

        if signal_log:
            cash_count = sum(1 for s in signal_log if s[1] == "CASH")
            exposures = [s[2] for s in signal_log if s[1] != "CASH"]
            avg_exp = np.mean(exposures) if exposures else 0
            print(f"Cash months: {cash_count}/{len(signal_log)} | Avg exposure when invested: {avg_exp:.0%}")

        print()
        all_results.append((period_name, results, signal_log))

    print("=" * 60)
    print("  DEFENSIVE BEAR THESIS")
    print("=" * 60)
    full = all_results[-1][1]
    db, spy, qqq, tqqq = full[0], full[1], full[2], full[3]
    print(f"Defensive Bear: {db['Annualized']} ann. | Sharpe {db['Sharpe']} | MDD {db['MDD']} | Calmar {db['Calmar']}")
    print(f"SPY B&H:        {spy['Annualized']} ann. | Sharpe {spy['Sharpe']} | MDD {spy['MDD']} | Calmar {spy['Calmar']}")
    print(f"QQQ B&H:        {qqq['Annualized']} ann. | Sharpe {qqq['Sharpe']} | MDD {qqq['MDD']} | Calmar {qqq['Calmar']}")
    print(f"TQQQ B&H:       {tqqq['Annualized']} ann. | Sharpe {tqqq['Sharpe']} | MDD {tqqq['MDD']} | Calmar {tqqq['Calmar']}")
    print()
    db_mdd = float(db['MDD'].strip('%'))
    spy_mdd = float(spy['MDD'].strip('%'))
    print(f"MDD 방어: SPY 대비 {abs(spy_mdd) - abs(db_mdd):.1f}%p 보호")
    print("변동성 타겟팅 = 급락 시 자동 포지션 축소. SMA 지연 없음.")

    return all_results


if __name__ == "__main__":
    results = main()
