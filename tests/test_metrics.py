"""Phase 4 Step 1: metrics.py TC"""

import pandas as pd
import pytest

from backtest.metrics import compute_metrics


@pytest.fixture()
def equity_curve():
    """100일 상승 equity curve"""
    dates = pd.date_range("2023-01-02", periods=100, freq="B")
    return [
        {"date": str(d.date()), "equity": 2000 + i * 10}
        for i, d in enumerate(dates)
    ]


@pytest.fixture()
def equity_curve_with_drawdown():
    """상승 후 하락 curve"""
    dates = pd.date_range("2023-01-02", periods=100, freq="B")
    curve = []
    for i, d in enumerate(dates[:50]):
        curve.append({"date": str(d.date()), "equity": 2000 + i * 20})
    for i, d in enumerate(dates[50:]):
        curve.append({"date": str(d.date()), "equity": 2980 - i * 15})
    return curve


# ── TC-1: total_return ──
def test_total_return(equity_curve):
    m = compute_metrics(equity_curve)
    expected = (2990 - 2000) / 2000
    assert m["total_return"] == pytest.approx(expected, rel=0.01)


# ── TC-2: max_drawdown ──
def test_max_drawdown(equity_curve_with_drawdown):
    m = compute_metrics(equity_curve_with_drawdown)
    assert m["max_drawdown"] < 0


# ── TC-3: sharpe_ratio ──
def test_sharpe_ratio(equity_curve):
    m = compute_metrics(equity_curve)
    assert isinstance(m["sharpe_ratio"], float)


# ── TC-4: calmar_ratio ──
def test_calmar_ratio(equity_curve_with_drawdown):
    m = compute_metrics(equity_curve_with_drawdown)
    assert isinstance(m["calmar_ratio"], float)


# ── TC-5: total_trades ──
def test_total_trades(equity_curve):
    m = compute_metrics(equity_curve, total_trades=15)
    assert m["total_trades"] == 15
    assert isinstance(m["total_trades"], int)


# ── TC-6: compute_metrics 반환 키 ──
def test_compute_metrics_keys(equity_curve):
    m = compute_metrics(equity_curve)
    for key in ("total_return", "max_drawdown", "sharpe_ratio", "calmar_ratio", "total_trades"):
        assert key in m


# ── TC-7: 빈 equity curve ──
def test_empty_equity_curve():
    m = compute_metrics([])
    assert m["total_return"] == 0.0
    assert m["max_drawdown"] == 0.0


# ── TC-8: annualized_return ──
def test_annualized_return(equity_curve):
    m = compute_metrics(equity_curve)
    assert "annualized_return" in m
    assert isinstance(m["annualized_return"], float)
