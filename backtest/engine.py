"""백테스트 엔진: 단일 종목 + 포트폴리오"""

import numpy as np
import pandas as pd

from backtest.portfolio import Portfolio
from backtest.rebalancer import (
    compute_target_weights_custom,
    compute_target_weights_equal,
    needs_rebalance,
    should_rebalance_on_date,
)
from backtest.strategies.base import Signal, Strategy
from config import CAPITAL, FeeModel


def run_backtest(
    df: pd.DataFrame,
    strategy: Strategy,
    capital: float = CAPITAL,
    fee_rate: float = FeeModel.STANDARD,
    with_reasons: bool = False,
) -> dict:
    if df.empty:
        return {
            "equity_curve": [],
            "total_trades": 0,
            "final_equity": capital,
            "trades": [],
            "params": strategy.params,
        }

    if with_reasons:
        signals, reasons = strategy.generate_signals_with_reasons(df)
    else:
        signals = strategy.generate_signals(df)
        reasons = None

    pf = Portfolio(capital=capital, fee_rate=fee_rate)
    position_open = False

    for date, row in df.iterrows():
        price = row["close"]
        sig = signals.get(date, Signal.HOLD)
        reason = reasons.get(date, "") if reasons is not None else ""

        if sig == Signal.BUY and not position_open:
            qty = pf.cash * 0.95 / (price * (1 + float(fee_rate)))
            if qty > 0:
                pf.buy("asset", price=price, qty=qty, reason=reason)
                position_open = True

        elif sig == Signal.SELL and position_open:
            qty = pf.positions.get("asset", 0)
            if qty > 0:
                pf.sell("asset", price=price, qty=qty, reason=reason)
                position_open = False

        pf.update_equity(str(date), {"asset": price})

    return {
        "equity_curve": pf.equity_curve,
        "total_trades": pf.trade_count,
        "final_equity": pf.get_total_equity({"asset": df.iloc[-1]["close"]}),
        "trades": pf.trade_log,
        "params": strategy.params,
    }


def run_backtest_fast(
    df: pd.DataFrame,
    strategy: Strategy,
    capital: float = CAPITAL,
    fee_rate: float = FeeModel.STANDARD,
) -> dict:
    """Grid search optimized backtest — no trade log, numpy equity curve."""
    if df.empty:
        return {
            "equity_curve_np": np.array([capital]),
            "total_trades": 0,
            "dates": np.array([]),
            "params": strategy.params,
        }

    signals = strategy.generate_signals(df)
    close = df["close"].values
    sig_values = signals.values.astype(int)
    n = len(close)

    # Filter to alternating BUY/SELL (respecting position state)
    trade_signals = np.zeros(n, dtype=int)
    in_position = False
    for i in range(n):
        if sig_values[i] == 1 and not in_position:
            trade_signals[i] = 1
            in_position = True
        elif sig_values[i] == -1 and in_position:
            trade_signals[i] = -1
            in_position = False

    # Compute equity with minimal loop over trade events only
    fee_buy = 1 + float(fee_rate)
    fee_sell = 1 - float(fee_rate)

    # Collect trade indices
    trade_idx = np.where(trade_signals != 0)[0]
    total_trades = len(trade_idx)

    # Build cash/qty state at each trade event
    cash_arr = np.empty(len(trade_idx) + 1)
    qty_arr = np.empty(len(trade_idx) + 1)
    cash_arr[0] = capital
    qty_arr[0] = 0.0

    for j, i in enumerate(trade_idx):
        c, q = cash_arr[j], qty_arr[j]
        if trade_signals[i] == 1:  # BUY
            alloc = c * 0.95
            buy_qty = alloc / (close[i] * fee_buy)
            cash_arr[j + 1] = c - close[i] * buy_qty * fee_buy
            qty_arr[j + 1] = buy_qty
        else:  # SELL
            cash_arr[j + 1] = c + close[i] * q * fee_sell
            qty_arr[j + 1] = 0.0

    # Build full equity curve using numpy segments
    equity = np.empty(n)
    boundaries = np.concatenate([[0], trade_idx, [n]])
    for j in range(len(boundaries) - 1):
        start = boundaries[j]
        end = boundaries[j + 1]
        if j < len(trade_idx) and start == trade_idx[j]:
            # After this trade event
            c, q = cash_arr[j + 1], qty_arr[j + 1]
            equity[start] = c + q * close[start]
            start += 1
            if start < end:
                equity[start:end] = c + q * close[start:end]
        else:
            c, q = cash_arr[j], qty_arr[j]
            equity[start:end] = c + q * close[start:end]

    return {
        "equity_curve_np": equity,
        "total_trades": total_trades,
        "dates": df.index.values,
        "params": strategy.params,
    }


def run_portfolio_backtest(
    data: dict[str, pd.DataFrame],
    strategy: Strategy,
    capital: float = CAPITAL,
    fee_rate: float = FeeModel.STANDARD,
    weights: dict[str, float] | None = None,
    rebalance_freq: str = "monthly",
) -> dict:
    symbols = list(data.keys())
    if not symbols:
        return {
            "equity_curve": [],
            "total_trades": 0,
            "final_equity": capital,
            "trades": [],
            "params": strategy.params,
        }

    if weights:
        target_weights = compute_target_weights_custom(weights)
    else:
        target_weights = compute_target_weights_equal(symbols)

    # 공통 날짜 인덱스
    common_idx = data[symbols[0]].index
    for sym in symbols[1:]:
        common_idx = common_idx.intersection(data[sym].index)

    pf = Portfolio(capital=capital, fee_rate=fee_rate)
    signals_map = {sym: strategy.generate_signals(data[sym]) for sym in symbols}
    open_positions: set[str] = set()

    # 초기 매수
    for sym in symbols:
        alloc = capital * target_weights.get(sym, 0)
        price = data[sym].loc[common_idx[0], "close"]
        qty = alloc * 0.95 / (price * (1 + float(fee_rate)))
        if qty > 0:
            pf.buy(sym, price=price, qty=qty)
            open_positions.add(sym)

    for date in common_idx:
        prices = {sym: data[sym].loc[date, "close"] for sym in symbols}

        # 전략 시그널 처리
        for sym in symbols:
            sig = signals_map[sym].get(date, Signal.HOLD)
            if sig == Signal.SELL and sym in open_positions:
                qty = pf.positions.get(sym, 0)
                if qty > 0:
                    pf.sell(sym, price=prices[sym], qty=qty)
                    open_positions.discard(sym)
            elif sig == Signal.BUY and sym not in open_positions:
                alloc = pf.cash * target_weights.get(sym, 0)
                qty = alloc * 0.95 / (prices[sym] * (1 + float(fee_rate)))
                if qty > 0:
                    pf.buy(sym, price=prices[sym], qty=qty)
                    open_positions.add(sym)

        # 리밸런싱
        if should_rebalance_on_date(date, rebalance_freq):
            current_weights = pf.get_weights(prices)
            if needs_rebalance(current_weights, target_weights):
                total_equity = pf.get_total_equity(prices)
                # 전량 매도 후 재매수
                for sym in list(pf.positions.keys()):
                    qty = pf.positions.get(sym, 0)
                    if qty > 0:
                        pf.sell(sym, price=prices[sym], qty=qty)
                open_positions.clear()
                for sym in symbols:
                    alloc = pf.cash * target_weights.get(sym, 0)
                    qty = alloc * 0.95 / (prices[sym] * (1 + float(fee_rate)))
                    if qty > 0:
                        pf.buy(sym, price=prices[sym], qty=qty)
                        open_positions.add(sym)

        pf.update_equity(str(date), prices)

    final_prices = {sym: data[sym].loc[common_idx[-1], "close"] for sym in symbols}
    return {
        "equity_curve": pf.equity_curve,
        "total_trades": pf.trade_count,
        "final_equity": pf.get_total_equity(final_prices),
        "trades": pf.trade_log,
        "params": strategy.params,
    }
