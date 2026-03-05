"""Phase 3 Step 1: Plotly 차트 함수 테스트 (TDD — 구현 전 failing 테스트)"""

import pandas as pd
import numpy as np
import pytest

go = pytest.importorskip("plotly.graph_objects", reason="plotly not installed")


@pytest.fixture
def mock_ohlcv():
    """50일 mock OHLCV 데이터."""
    dates = pd.date_range("2023-01-01", periods=50, freq="B")
    np.random.seed(42)
    close = 100 + np.cumsum(np.random.randn(50))
    return pd.DataFrame(
        {
            "Open": close - 0.5,
            "High": close + 1.0,
            "Low": close - 1.0,
            "Close": close,
            "Volume": np.random.randint(1000, 5000, 50),
        },
        index=dates,
    )


@pytest.fixture
def mock_trades():
    """BUY/SELL 거래 로그."""
    return [
        {"date": pd.Timestamp("2023-01-10"), "action": "BUY", "price": 101.0, "reason": "BB 하단 돌파"},
        {"date": pd.Timestamp("2023-01-20"), "action": "SELL", "price": 105.0, "reason": "RSI 과매수"},
        {"date": pd.Timestamp("2023-02-01"), "action": "BUY", "price": 99.0, "reason": "MACD 골든크로스"},
        {"date": pd.Timestamp("2023-02-15"), "action": "SELL", "price": 108.0, "reason": "BB 상단 돌파"},
    ]


@pytest.fixture
def mock_equity_curve():
    """50일 equity curve."""
    dates = pd.date_range("2023-01-01", periods=50, freq="B")
    return pd.Series(
        100 + np.arange(50) * 0.5 + np.random.randn(50) * 2,
        index=dates,
    )


@pytest.fixture
def mock_bh_curve():
    """50일 Buy & Hold equity curve."""
    dates = pd.date_range("2023-01-01", periods=50, freq="B")
    return pd.Series(
        100 + np.arange(50) * 0.3,
        index=dates,
    )


# --- TC-1: plotly in requirements.txt ---
def test_plotly_in_requirements():
    with open("requirements.txt") as f:
        content = f.read()
    assert "plotly" in content.lower()


# --- TC-2: report_html 모듈 import ---
def test_report_html_importable():
    from backtest import report_html  # noqa: F401


# --- TC-3: create_symbol_chart 반환 타입 ---
def test_create_symbol_chart_returns_figure(mock_ohlcv, mock_trades, mock_equity_curve):
    from backtest.report_html import create_symbol_chart

    fig = create_symbol_chart(mock_ohlcv, mock_trades, mock_equity_curve, "TQQQ")
    assert isinstance(fig, go.Figure)


# --- TC-4: BUY/SELL 마커 trace 포함 ---
def test_create_symbol_chart_has_buy_sell_markers(mock_ohlcv, mock_trades, mock_equity_curve):
    from backtest.report_html import create_symbol_chart

    fig = create_symbol_chart(mock_ohlcv, mock_trades, mock_equity_curve, "TQQQ")
    trace_names = [t.name for t in fig.data]
    assert "BUY" in trace_names
    assert "SELL" in trace_names


# --- TC-5: hover customdata에 reason 포함 ---
def test_create_symbol_chart_hover_has_reason(mock_ohlcv, mock_trades, mock_equity_curve):
    from backtest.report_html import create_symbol_chart

    fig = create_symbol_chart(mock_ohlcv, mock_trades, mock_equity_curve, "TQQQ")
    buy_traces = [t for t in fig.data if t.name == "BUY"]
    assert len(buy_traces) == 1
    buy_trace = buy_traces[0]
    # customdata should contain reason strings
    assert buy_trace.customdata is not None
    assert len(buy_trace.customdata) > 0


# --- TC-6: create_preset_comparison_chart 반환 타입 ---
def test_create_preset_comparison_chart_returns_figure():
    from backtest.report_html import create_preset_comparison_chart

    preset_results = {
        "growth": {"total_return": 0.25, "max_drawdown": -0.15, "sharpe_ratio": 1.2},
        "safe": {"total_return": 0.10, "max_drawdown": -0.05, "sharpe_ratio": 0.8},
    }
    fig = create_preset_comparison_chart(preset_results)
    assert isinstance(fig, go.Figure)


# --- TC-7: create_period_comparison_chart 반환 타입 ---
def test_create_period_comparison_chart_returns_figure():
    from backtest.report_html import create_period_comparison_chart

    period_results = {
        "1Y": {"total_return": 0.15, "sharpe_ratio": 1.0},
        "3Y": {"total_return": 0.45, "sharpe_ratio": 1.3},
    }
    fig = create_period_comparison_chart(period_results, "TQQQ")
    assert isinstance(fig, go.Figure)


# --- TC-8: B&H curve 오버레이 ---
def test_create_symbol_chart_bh_overlay(mock_ohlcv, mock_trades, mock_equity_curve, mock_bh_curve):
    from backtest.report_html import create_symbol_chart

    fig = create_symbol_chart(
        mock_ohlcv, mock_trades, mock_equity_curve, "TQQQ", bh_curve=mock_bh_curve
    )
    trace_names = [t.name for t in fig.data]
    assert any("B&H" in (n or "") or "Buy" in (n or "") for n in trace_names)
