"""포트폴리오 프리셋 비교 모듈"""

import pandas as pd

from backtest.buyhold import compute_buyhold
from backtest.engine import run_backtest, run_portfolio_backtest
from backtest.metrics import compute_metrics
from backtest.strategies.base import Strategy
from config import (
    CAPITAL,
    FeeModel,
    PRESET_ALL_3X,
    PRESET_GROWTH,
    PRESET_MIXED,
    PRESET_SAFE,
)

PRESETS = {
    "growth": PRESET_GROWTH,
    "safe": PRESET_SAFE,
    "mixed": PRESET_MIXED,
    "all_3x": PRESET_ALL_3X,
}


def run_single_vs_portfolio(
    data: dict[str, pd.DataFrame],
    strategy: Strategy,
    weights: dict[str, float],
    capital: float = CAPITAL,
    fee_rate: float = FeeModel.STANDARD,
) -> dict:
    single_results = {}
    for sym, df in data.items():
        bt = run_backtest(df, strategy, capital=capital, fee_rate=fee_rate)
        bh = compute_buyhold(df, capital=capital, fee_rate=fee_rate)
        m = compute_metrics(bt["equity_curve"], total_trades=bt["total_trades"])
        m["excess_return"] = m["total_return"] - bh["total_return"]
        single_results[sym] = m

    portfolio_result = run_portfolio_backtest(
        data, strategy, capital=capital, fee_rate=fee_rate, weights=weights
    )
    pm = compute_metrics(
        portfolio_result["equity_curve"], total_trades=portfolio_result["total_trades"]
    )

    return {
        "single_results": single_results,
        "portfolio_result": pm,
    }


def run_preset_comparison(
    data: dict[str, pd.DataFrame],
    strategy: Strategy,
    presets: dict[str, dict[str, float]] | None = None,
    capital: float = CAPITAL,
    fee_rate: float = FeeModel.STANDARD,
) -> dict:
    if presets is None:
        presets = PRESETS

    if not presets:
        return {}

    results = {}
    for name, weights in presets.items():
        symbols = list(weights.keys())
        subset = {s: data[s] for s in symbols if s in data}
        if not subset:
            continue

        bt = run_portfolio_backtest(
            subset, strategy, capital=capital, fee_rate=fee_rate, weights=weights
        )
        m = compute_metrics(bt["equity_curve"], total_trades=bt["total_trades"])

        # B&H 대비 (첫 번째 심볼 기준)
        first_sym = list(subset.keys())[0]
        bh = compute_buyhold(subset[first_sym], capital=capital, fee_rate=fee_rate)
        m["excess_return"] = m["total_return"] - bh["total_return"]

        results[name] = m

    return results
