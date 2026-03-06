"""성과 지표 계산"""

import numpy as np
import pandas as pd


def compute_metrics(equity_curve: list[dict], total_trades: int = 0, periods_per_year: int = 252) -> dict:
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
        sharpe_ratio = daily_returns.mean() / daily_returns.std() * np.sqrt(periods_per_year)
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


def compute_metrics_fast(
    equity: np.ndarray,
    dates: np.ndarray,
    total_trades: int = 0,
    periods_per_year: int = 252,
) -> dict:
    """Numpy array based metrics — no dict/Series overhead."""
    if len(equity) < 2:
        return {
            "total_return": 0.0,
            "annualized_return": 0.0,
            "max_drawdown": 0.0,
            "sharpe_ratio": 0.0,
            "calmar_ratio": 0.0,
            "total_trades": total_trades,
        }

    initial = equity[0]
    final = equity[-1]
    total_return = (final - initial) / initial if initial != 0 else 0.0

    days = (dates[-1] - dates[0]) / np.timedelta64(1, "D")
    if days > 0 and initial > 0:
        annualized_return = (final / initial) ** (365 / days) - 1
    else:
        annualized_return = 0.0

    peak = np.maximum.accumulate(equity)
    drawdown = (equity - peak) / peak
    max_drawdown = float(np.min(drawdown))

    daily_returns = np.diff(equity) / equity[:-1]
    std = np.std(daily_returns, ddof=1) if len(daily_returns) > 1 else 0.0
    if std > 0:
        sharpe_ratio = float(np.mean(daily_returns) / std * np.sqrt(periods_per_year))
    else:
        sharpe_ratio = 0.0

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
