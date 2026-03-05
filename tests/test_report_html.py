"""Phase 3 Step 1-2: Plotly 차트 함수 + HTML 보고서 조립 테스트"""

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


# ============================================================
# Step 2: HTML 보고서 조립 테스트
# ============================================================

@pytest.fixture
def mock_grid_results():
    """Grid search top 5 결과."""
    return [
        {
            "params": {"bb_window": 20, "rsi_window": 14},
            "total_return": 0.30,
            "sharpe_ratio": 1.5,
            "max_drawdown": -0.10,
            "total_trades": 42,
        },
        {
            "params": {"bb_window": 25, "rsi_window": 10},
            "total_return": 0.25,
            "sharpe_ratio": 1.3,
            "max_drawdown": -0.12,
            "total_trades": 38,
        },
    ]


@pytest.fixture
def mock_symbol_data(mock_ohlcv, mock_trades, mock_equity_curve, mock_bh_curve):
    """종목별 데이터 dict."""
    return {
        "TQQQ": {
            "ohlcv": mock_ohlcv,
            "trades": mock_trades,
            "equity_curve": mock_equity_curve,
            "bh_curve": mock_bh_curve,
            "metrics": {"total_return": 0.25, "sharpe_ratio": 1.2, "max_drawdown": -0.10},
        },
        "SOXL": {
            "ohlcv": mock_ohlcv.copy(),
            "trades": mock_trades[:2],
            "equity_curve": mock_equity_curve.copy(),
            "bh_curve": mock_bh_curve.copy(),
            "metrics": {"total_return": 0.15, "sharpe_ratio": 0.9, "max_drawdown": -0.20},
        },
    }


# --- TC-9: create_grid_results_table 반환 타입 ---
def test_create_grid_results_table_returns_html(mock_grid_results):
    from backtest.report_html import create_grid_results_table

    html = create_grid_results_table(mock_grid_results)
    assert isinstance(html, str)
    assert "<table" in html.lower()


# --- TC-10: grid results table에 파라미터 + 메트릭스 포함 ---
def test_create_grid_results_table_contains_metrics(mock_grid_results):
    from backtest.report_html import create_grid_results_table

    html = create_grid_results_table(mock_grid_results)
    assert "total_return" in html or "수익률" in html or "1.5" in html
    assert "bb_window" in html or "20" in html


# --- TC-11: generate_full_html_report 파일 생성 ---
def test_generate_full_html_report_creates_file(tmp_path, mock_symbol_data, mock_grid_results):
    from backtest.report_html import generate_full_html_report

    output_path = tmp_path / "report.html"
    result = generate_full_html_report(
        symbol_data=mock_symbol_data,
        grid_results=mock_grid_results,
        output_path=str(output_path),
    )
    assert output_path.exists()
    assert output_path.stat().st_size > 0


# --- TC-12: HTML에 plotly 스크립트 포함 ---
def test_full_html_report_has_plotly_script(tmp_path, mock_symbol_data, mock_grid_results):
    from backtest.report_html import generate_full_html_report

    output_path = tmp_path / "report.html"
    generate_full_html_report(
        symbol_data=mock_symbol_data,
        grid_results=mock_grid_results,
        output_path=str(output_path),
    )
    content = output_path.read_text()
    assert "plotly" in content.lower()


# --- TC-13: HTML에 종목별 앵커 네비게이션 ---
def test_full_html_report_has_symbol_anchors(tmp_path, mock_symbol_data, mock_grid_results):
    from backtest.report_html import generate_full_html_report

    output_path = tmp_path / "report.html"
    generate_full_html_report(
        symbol_data=mock_symbol_data,
        grid_results=mock_grid_results,
        output_path=str(output_path),
    )
    content = output_path.read_text()
    for symbol in mock_symbol_data:
        assert f'id="{symbol}"' in content or f"#{symbol}" in content


# --- TC-14: HTML에 종목별 차트 섹션 포함 ---
def test_full_html_report_has_symbol_sections(tmp_path, mock_symbol_data, mock_grid_results):
    from backtest.report_html import generate_full_html_report

    output_path = tmp_path / "report.html"
    generate_full_html_report(
        symbol_data=mock_symbol_data,
        grid_results=mock_grid_results,
        output_path=str(output_path),
    )
    content = output_path.read_text()
    for symbol in mock_symbol_data:
        assert symbol in content


# --- TC-15: generate_full_html_report 반환값 ---
def test_generate_full_html_report_returns_path(tmp_path, mock_symbol_data, mock_grid_results):
    from backtest.report_html import generate_full_html_report

    output_path = tmp_path / "report.html"
    result = generate_full_html_report(
        symbol_data=mock_symbol_data,
        grid_results=mock_grid_results,
        output_path=str(output_path),
    )
    assert isinstance(result, str)
    assert "report.html" in result
