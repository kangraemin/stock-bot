"""3인 전문가 합의 전략 백테스트

전략 구조:
├── Core (60%): QQQ Buy & Hold
├── Leverage Sleeve (25%): TQQQ ↔ QQQ ↔ Cash (변동성 기반)
└── Momentum Satellite (15%): 상위 모멘텀 2종목 월간 로테이션

비교 대상: SPY B&H, QQQ B&H, TQQQ B&H
"""

import sys
sys.path.insert(0, ".")

import numpy as np
import pandas as pd
from backtest.data_loader import load_single
from config import FeeModel

CAPITAL = 10_000_000
FEE = float(FeeModel.STANDARD)
MOMENTUM_UNIVERSE = ["NVDA", "AAPL", "TSLA", "MSFT", "AMZN", "GOOGL"]


def realized_vol(close: pd.Series, window: int = 21) -> pd.Series:
    """Annualized realized volatility (VIX proxy)."""
    log_ret = np.log(close / close.shift(1))
    return log_ret.rolling(window).std() * np.sqrt(252) * 100


def compute_momentum_score(close: pd.Series) -> float:
    """Composite momentum: 50% ROC63 + 30% ROC21 + 20% ROC126."""
    if len(close) < 127:
        return -999
    roc63 = (close.iloc[-1] / close.iloc[-63] - 1) * 100 if len(close) >= 64 else 0
    roc21 = (close.iloc[-1] / close.iloc[-21] - 1) * 100 if len(close) >= 22 else 0
    roc126 = (close.iloc[-1] / close.iloc[-126] - 1) * 100 if len(close) >= 127 else 0
    return 0.5 * roc63 + 0.3 * roc21 + 0.2 * roc126


def get_leverage_allocation(vol: float) -> dict:
    """VIX proxy 기반 레버리지 슬리브 배분."""
    if np.isnan(vol):
        return {"TQQQ": 0, "QQQ": 1.0, "CASH": 0}
    if vol < 15:
        return {"TQQQ": 1.0, "QQQ": 0, "CASH": 0}
    elif vol < 20:
        return {"TQQQ": 0.5, "QQQ": 0.5, "CASH": 0}
    elif vol < 25:
        return {"TQQQ": 0, "QQQ": 1.0, "CASH": 0}
    elif vol < 30:
        return {"TQQQ": 0, "QQQ": 0.5, "CASH": 0.5}
    else:
        return {"TQQQ": 0, "QQQ": 0, "CASH": 1.0}


def run_consensus_strategy(
    data: dict[str, pd.DataFrame],
    capital: float = CAPITAL,
    fee_rate: float = FEE,
    core_weight: float = 0.60,
    leverage_weight: float = 0.25,
    satellite_weight: float = 0.15,
    rebalance_freq: str = "weekly",
):
    """합의 전략 백테스트."""
    qqq = data["QQQ"]
    tqqq = data["TQQQ"]
    spy = data["SPY"]

    # Common dates where all key assets exist
    common_idx = qqq.index.intersection(tqqq.index).intersection(spy.index)
    for sym in MOMENTUM_UNIVERSE:
        if sym in data:
            common_idx = common_idx.intersection(data[sym].index)
    common_idx = common_idx.sort_values()

    if len(common_idx) < 200:
        print("Not enough common dates")
        return None

    # Realized vol on SPY (VIX proxy)
    spy_vol = realized_vol(spy.loc[common_idx, "close"])

    # State
    cash = capital
    positions = {}  # {symbol: qty}
    core_qty = 0  # Core QQQ position — NEVER SOLD
    equity_history = []
    trade_count = 0
    last_rebalance = None
    prev_lev_alloc = None
    prev_mom_picks = []

    # Track allocations for reporting
    allocation_log = []

    # Track which positions are leverage/satellite (not core)
    tactical_positions = {}  # {symbol: qty} — only lev sleeve + satellite

    for i, date in enumerate(common_idx):
        prices = {}
        for sym in ["QQQ", "TQQQ", "SPY"] + MOMENTUM_UNIVERSE:
            if sym in data and date in data[sym].index:
                prices[sym] = data[sym].loc[date, "close"]

        # Initial buy (warmup complete)
        if core_qty == 0 and i >= 200 and "QQQ" in prices:
            # Buy core QQQ — NEVER SELL THIS
            core_alloc = capital * core_weight
            core_qty = core_alloc / (prices["QQQ"] * (1 + fee_rate))
            cash -= core_qty * prices["QQQ"] * (1 + fee_rate)
            trade_count += 1
            last_rebalance = date

        # Check if tactical rebalance needed
        do_rebalance = False
        if core_qty > 0 and last_rebalance is not None:
            if rebalance_freq == "weekly" and (date - last_rebalance).days >= 5:
                do_rebalance = True
            elif rebalance_freq == "monthly" and (date - last_rebalance).days >= 20:
                do_rebalance = True

        if do_rebalance and "QQQ" in prices and "TQQQ" in prices:
            # Compute total equity
            total_equity = cash + core_qty * prices["QQQ"]
            for sym, qty in tactical_positions.items():
                if sym in prices:
                    total_equity += qty * prices[sym]

            # --- SELL ONLY TACTICAL POSITIONS (not core) ---
            for sym, qty in list(tactical_positions.items()):
                if qty > 0 and sym in prices:
                    cash += qty * prices[sym] * (1 - fee_rate)
                    trade_count += 1
            tactical_positions = {}

            tactical_cash = cash  # available for lev + satellite

            # --- LEVERAGE SLEEVE: 25% of total equity ---
            vol_now = spy_vol.loc[date] if date in spy_vol.index else 20
            lev_alloc_map = get_leverage_allocation(vol_now)
            lev_total = total_equity * leverage_weight

            for sym, pct in lev_alloc_map.items():
                if pct <= 0 or sym == "CASH":
                    continue
                alloc = lev_total * pct
                qty = alloc / (prices[sym] * (1 + fee_rate))
                tactical_positions[sym] = tactical_positions.get(sym, 0) + qty
                cash -= qty * prices[sym] * (1 + fee_rate)
                trade_count += 1

            # --- MOMENTUM SATELLITE: 15% of total equity ---
            sat_total = total_equity * satellite_weight
            mom_scores = {}
            for sym in MOMENTUM_UNIVERSE:
                if sym in data and date in data[sym].index:
                    loc = data[sym].index.get_loc(date)
                    if loc >= 126:
                        close_slice = data[sym]["close"].iloc[:loc + 1]
                        score = compute_momentum_score(close_slice)
                        roc63 = (close_slice.iloc[-1] / close_slice.iloc[-63] - 1) if len(close_slice) >= 64 else -1
                        if roc63 > 0:
                            mom_scores[sym] = score

            if mom_scores:
                sorted_mom = sorted(mom_scores.items(), key=lambda x: x[1], reverse=True)
                top_n = min(2, len(sorted_mom))
                per_stock = sat_total / top_n
                for sym, _ in sorted_mom[:top_n]:
                    qty = per_stock / (prices[sym] * (1 + fee_rate))
                    tactical_positions[sym] = tactical_positions.get(sym, 0) + qty
                    cash -= qty * prices[sym] * (1 + fee_rate)
                    trade_count += 1
            else:
                # Fallback: put satellite into QQQ tactical
                qty = sat_total / (prices["QQQ"] * (1 + fee_rate))
                tactical_positions["QQQ"] = tactical_positions.get("QQQ", 0) + qty
                cash -= qty * prices["QQQ"] * (1 + fee_rate)
                trade_count += 1

            last_rebalance = date
            allocation_log.append({
                "date": date, "vol": vol_now,
                "lev": lev_alloc_map,
                "mom_picks": list(mom_scores.keys())[:2] if mom_scores else ["QQQ"],
            })

        # Compute equity
        equity = cash
        if core_qty > 0 and "QQQ" in prices:
            equity += core_qty * prices["QQQ"]
        for sym, qty in tactical_positions.items():
            if sym in prices:
                equity += qty * prices[sym]

        equity_history.append({"date": date, "equity": equity})

    return {
        "equity_curve": equity_history,
        "trade_count": trade_count,
        "allocation_log": allocation_log,
        "common_idx": common_idx,
    }


def compute_metrics_from_curve(curve: list[dict]) -> dict:
    eq = pd.Series([e["equity"] for e in curve])
    dates = pd.to_datetime([e["date"] for e in curve])

    initial, final = eq.iloc[0], eq.iloc[-1]
    total_return = (final - initial) / initial
    days = (dates[-1] - dates[0]).days
    ann_return = (final / initial) ** (365 / days) - 1 if days > 0 else 0

    peak = eq.expanding().max()
    dd = (eq - peak) / peak
    mdd = dd.min()

    daily_ret = eq.pct_change().dropna()
    sharpe = (daily_ret.mean() / daily_ret.std() * np.sqrt(252)) if daily_ret.std() > 0 else 0
    calmar = ann_return / abs(mdd) if mdd != 0 else 0

    # Recovery time (max consecutive days below peak)
    below_peak = eq < peak
    groups = (~below_peak).cumsum()
    recovery_days = below_peak.groupby(groups).sum().max() if below_peak.any() else 0

    return {
        "total_return": total_return,
        "annualized_return": ann_return,
        "max_drawdown": mdd,
        "sharpe_ratio": sharpe,
        "calmar_ratio": calmar,
        "recovery_days": int(recovery_days),
    }


def buyhold_curve(df: pd.DataFrame, common_idx, capital: float, fee_rate: float) -> list[dict]:
    """Simple B&H equity curve on common dates."""
    first_price = df.loc[common_idx[0], "close"]
    qty = capital * 0.95 / (first_price * (1 + fee_rate))
    leftover = capital - qty * first_price * (1 + fee_rate)

    curve = []
    for date in common_idx:
        if date in df.index:
            eq = leftover + qty * df.loc[date, "close"]
            curve.append({"date": date, "equity": eq})
    return curve


def slice_period(common_idx, years):
    end = common_idx[-1]
    start = end - pd.DateOffset(years=years)
    return common_idx[common_idx >= start]


def main():
    from backtest.data_loader import load_single

    # Load all data
    data = {}
    for sym in ["QQQ", "TQQQ", "SPY"] + MOMENTUM_UNIVERSE:
        try:
            data[sym] = load_single(sym)
        except FileNotFoundError:
            print(f"WARNING: {sym} not found, skipping")

    print("=" * 120)
    print("CONSENSUS STRATEGY BACKTEST: VIX기반 레버리지 + Core-Satellite")
    print("=" * 120)
    print(f"Core 60% QQQ B&H | Leverage 25% TQQQ/QQQ/Cash (vol-based) | Satellite 15% Momentum Top2")
    print(f"Capital: ${CAPITAL:,.0f} | Fee: {FEE*100:.2f}%")
    print()

    # Run main strategy
    result = run_consensus_strategy(data, capital=CAPITAL, fee_rate=FEE)
    if not result:
        print("FAILED")
        return

    common_idx = result["common_idx"]

    # B&H benchmarks on same dates
    spy_bh = buyhold_curve(data["SPY"], common_idx, CAPITAL, FEE)
    qqq_bh = buyhold_curve(data["QQQ"], common_idx, CAPITAL, FEE)
    tqqq_bh = buyhold_curve(data["TQQQ"], common_idx, CAPITAL, FEE)

    # Period analysis
    for period_name, years in [("3y", 3), ("5y", 5), ("10y", 10), ("Full", None)]:
        if years:
            period_idx = slice_period(common_idx, years)
        else:
            period_idx = common_idx

        # Filter curves to period
        start_date = period_idx[0]

        def filter_curve(curve, start):
            return [e for e in curve if e["date"] >= start]

        strat_curve = filter_curve(result["equity_curve"], start_date)
        spy_curve = filter_curve(spy_bh, start_date)
        qqq_curve = filter_curve(qqq_bh, start_date)
        tqqq_curve = filter_curve(tqqq_bh, start_date)

        if len(strat_curve) < 60:
            continue

        # Rebase all to same starting equity
        def rebase(curve):
            if not curve:
                return curve
            base = curve[0]["equity"]
            return [{"date": e["date"], "equity": e["equity"] / base * CAPITAL} for e in curve]

        strat_curve = rebase(strat_curve)
        spy_curve = rebase(spy_curve)
        qqq_curve = rebase(qqq_curve)
        tqqq_curve = rebase(tqqq_curve)

        strat_m = compute_metrics_from_curve(strat_curve)
        spy_m = compute_metrics_from_curve(spy_curve)
        qqq_m = compute_metrics_from_curve(qqq_curve)
        tqqq_m = compute_metrics_from_curve(tqqq_curve)

        print(f"\n{'=' * 100}")
        label = f"{period_name} ({strat_curve[0]['date'].date()} ~ {strat_curve[-1]['date'].date()})"
        print(f"  {label}")
        print(f"{'=' * 100}")
        print(f"  {'Strategy':25s} | {'Return':>10s} | {'Annual':>10s} | {'Sharpe':>8s} | {'MDD':>8s} | {'Calmar':>8s} | {'Recovery':>10s}")
        print(f"  {'-'*25}-+-{'-'*10}-+-{'-'*10}-+-{'-'*8}-+-{'-'*8}-+-{'-'*8}-+-{'-'*10}")

        for name, m in [
            ("CONSENSUS (합의전략)", strat_m),
            ("SPY B&H", spy_m),
            ("QQQ B&H", qqq_m),
            ("TQQQ B&H", tqqq_m),
        ]:
            print(f"  {name:25s} | {m['total_return']*100:>+9.1f}% | {m['annualized_return']*100:>+9.1f}% | {m['sharpe_ratio']:>8.2f} | {m['max_drawdown']*100:>7.1f}% | {m['calmar_ratio']:>8.2f} | {m['recovery_days']:>8d} days")

        # Alpha vs each benchmark
        print(f"\n  Alpha vs SPY: {(strat_m['total_return'] - spy_m['total_return'])*100:+.1f}%")
        print(f"  Alpha vs QQQ: {(strat_m['total_return'] - qqq_m['total_return'])*100:+.1f}%")
        print(f"  Alpha vs TQQQ: {(strat_m['total_return'] - tqqq_m['total_return'])*100:+.1f}%")

    # Allocation analysis
    print(f"\n\n{'=' * 100}")
    print("ALLOCATION HISTORY (recent 20 rebalances)")
    print(f"{'=' * 100}")
    for entry in result["allocation_log"][-20:]:
        vol = entry["vol"]
        lev = entry["lev"]
        tqqq_pct = lev.get("TQQQ", 0) * 100
        qqq_pct = lev.get("QQQ", 0) * 100
        cash_pct = lev.get("CASH", 0) * 100
        picks = ", ".join(entry["mom_picks"][:2])
        print(f"  {entry['date'].date()} | Vol: {vol:5.1f}% | Lev Sleeve: TQQQ {tqqq_pct:.0f}% QQQ {qqq_pct:.0f}% Cash {cash_pct:.0f}% | Mom: {picks}")

    print(f"\n  Total trades: {result['trade_count']}")


if __name__ == "__main__":
    main()
