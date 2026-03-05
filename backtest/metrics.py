"""성과 지표 계산"""

import numpy as np
import pandas as pd


def compute_metrics(equity_curve: list[dict], total_trades: int = 0) -> dict:
    if not equity_curve:
        return {
            "total_return": 0.0,
            "annualized_return": 0.0,
            "max_drawdown": 0.0,
            "sharpe_ratio": 0.0,
            "calmar_ratio": 0.0,
            "total_trades": total_trades,
        }

    equities = pd.Series([e["equity"] for e in equity_curve])
    dates = pd.to_datetime([e["date"] for e in equity_curve])

    initial = equities.iloc[0]
    final = equities.iloc[-1]

    total_return = (final - initial) / initial if initial != 0 else 0.0

    # 연간 수익률
    days = (dates[-1] - dates[0]).days
    if days > 0 and initial > 0:
        annualized_return = (final / initial) ** (365 / days) - 1
    else:
        annualized_return = 0.0

    # MDD
    peak = equities.expanding().max()
    drawdown = (equities - peak) / peak
    max_drawdown = drawdown.min()

    # Sharpe (일간 수익률 기반, 무위험=0)
    daily_returns = equities.pct_change().dropna()
    if len(daily_returns) > 1 and daily_returns.std() > 0:
        sharpe_ratio = daily_returns.mean() / daily_returns.std() * np.sqrt(252)
    else:
        sharpe_ratio = 0.0

    # Calmar
    if max_drawdown != 0:
        calmar_ratio = annualized_return / abs(max_drawdown)
    else:
        calmar_ratio = 0.0

    return {
        "total_return": total_return,
        "annualized_return": annualized_return,
        "max_drawdown": max_drawdown,
        "sharpe_ratio": sharpe_ratio,
        "calmar_ratio": calmar_ratio,
        "total_trades": total_trades,
    }
