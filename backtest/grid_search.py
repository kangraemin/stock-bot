"""파라미터 그리드 서치"""

import itertools

import pandas as pd

from backtest.buyhold import compute_buyhold
from backtest.engine import run_backtest
from backtest.metrics import compute_metrics
from backtest.strategies.bb_rsi_ema import BbRsiEma
from config import CAPITAL, FeeModel

DEFAULT_GRID = {
    "bb_window": [15, 20, 25, 30],
    "bb_std": [1.5, 2.0, 2.5, 3.0],
    "rsi_window": [10, 14, 21],
    "ema_window": [20, 50, 100, 200],
}


def generate_param_combos(grid: dict | None = None) -> list[dict]:
    if grid is None:
        grid = DEFAULT_GRID
    keys = list(grid.keys())
    values = list(grid.values())
    return [dict(zip(keys, combo)) for combo in itertools.product(*values)]


def run_grid_search(
    df: pd.DataFrame,
    grid: dict | None = None,
    capital: float = CAPITAL,
    fee_rate: float = FeeModel.STANDARD,
    top_n: int | None = None,
) -> list[dict]:
    combos = generate_param_combos(grid)
    bh = compute_buyhold(df, capital=capital, fee_rate=fee_rate)
    bh_return = bh["total_return"]

    results = []
    for params in combos:
        strategy = BbRsiEma(**params)
        bt = run_backtest(df, strategy, capital=capital, fee_rate=fee_rate)
        metrics = compute_metrics(bt["equity_curve"], total_trades=bt["total_trades"])
        s_return = metrics["total_return"]
        results.append({
            "params": params,
            "total_trades": metrics["total_trades"],
            "vs_buyhold_excess": s_return - bh_return,
            **metrics,
        })

    results.sort(key=lambda x: x.get("sharpe_ratio", 0), reverse=True)

    if top_n:
        results = results[:top_n]

    return results
