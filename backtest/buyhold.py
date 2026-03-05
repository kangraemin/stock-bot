"""Buy & Hold 비교 모듈"""

import pandas as pd

from config import CAPITAL, FeeModel


def compute_buyhold(
    df: pd.DataFrame,
    capital: float = CAPITAL,
    fee_rate: float = FeeModel.STANDARD,
) -> dict:
    if df.empty:
        return {"final_equity": capital, "total_return": 0.0, "equity_curve": []}

    first_price = df.iloc[0]["close"]
    qty = capital / (first_price * (1 + float(fee_rate)))
    fee_cost = first_price * qty * float(fee_rate)
    remaining_cash = capital - first_price * qty - fee_cost

    curve = []
    for date, row in df.iterrows():
        equity = remaining_cash + row["close"] * qty
        curve.append({"date": str(date), "equity": equity})

    final = curve[-1]["equity"]
    return {
        "final_equity": final,
        "total_return": (final - capital) / capital,
        "equity_curve": curve,
    }


def compare_vs_buyhold(strategy_result: dict, buyhold_result: dict) -> dict:
    s_ret = strategy_result.get("total_return", 0)
    if "total_return" not in strategy_result:
        s_final = strategy_result.get("final_equity", 0)
        s_ret = (s_final - CAPITAL) / CAPITAL if CAPITAL else 0

    b_ret = buyhold_result.get("total_return", 0)
    return {
        "strategy_return": s_ret,
        "buyhold_return": b_ret,
        "excess_return": s_ret - b_ret,
    }


def compare_by_period(
    df: pd.DataFrame,
    strategy_result: dict,
    periods: list[str] | None = None,
    capital: float = CAPITAL,
    fee_rate: float = FeeModel.STANDARD,
) -> list[dict]:
    if periods is None:
        periods = ["1y", "3y", "5y"]

    results = []
    for period in periods:
        years = int(period.replace("y", ""))
        end = df.index[-1]
        start = end - pd.DateOffset(years=years)
        sub = df[df.index >= start]
        if sub.empty:
            continue
        bh = compute_buyhold(sub, capital=capital, fee_rate=fee_rate)
        results.append({"period": period, **bh})
    return results
