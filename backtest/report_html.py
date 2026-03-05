"""Plotly 기반 인터랙티브 차트 생성"""

import pandas as pd
import plotly.graph_objects as go


def create_symbol_chart(
    df: pd.DataFrame,
    trades: list[dict],
    equity_curve: pd.Series,
    symbol: str,
    bh_curve: pd.Series | None = None,
) -> go.Figure:
    fig = go.Figure()

    # 가격 close 컬럼 (대소문자 호환)
    close_col = "Close" if "Close" in df.columns else "close"
    fig.add_trace(go.Scatter(x=df.index, y=df[close_col], name=f"{symbol} Close"))

    # BUY 마커
    buy_trades = [t for t in trades if t["action"].upper() == "BUY"]
    if buy_trades:
        fig.add_trace(go.Scatter(
            x=[t["date"] for t in buy_trades],
            y=[t["price"] for t in buy_trades],
            mode="markers",
            marker=dict(symbol="triangle-up", color="green", size=12),
            name="BUY",
            customdata=[[t.get("reason", "")] for t in buy_trades],
            hovertemplate="%{x}<br>Price: %{y}<br>Reason: %{customdata[0]}<extra></extra>",
        ))

    # SELL 마커
    sell_trades = [t for t in trades if t["action"].upper() == "SELL"]
    if sell_trades:
        fig.add_trace(go.Scatter(
            x=[t["date"] for t in sell_trades],
            y=[t["price"] for t in sell_trades],
            mode="markers",
            marker=dict(symbol="triangle-down", color="red", size=12),
            name="SELL",
            customdata=[[t.get("reason", "")] for t in sell_trades],
            hovertemplate="%{x}<br>Price: %{y}<br>Reason: %{customdata[0]}<extra></extra>",
        ))

    # Equity curve
    fig.add_trace(go.Scatter(x=equity_curve.index, y=equity_curve.values, name="Equity"))

    # B&H curve
    if bh_curve is not None:
        fig.add_trace(go.Scatter(x=bh_curve.index, y=bh_curve.values, name="Buy & Hold"))

    fig.update_layout(title=f"{symbol} Backtest", xaxis_title="Date", yaxis_title="Price")
    return fig


def create_preset_comparison_chart(preset_results: dict) -> go.Figure:
    fig = go.Figure()
    names = list(preset_results.keys())
    metrics_keys = ["total_return", "max_drawdown", "sharpe_ratio"]

    for metric in metrics_keys:
        values = [preset_results[n].get(metric, 0) for n in names]
        fig.add_trace(go.Bar(x=names, y=values, name=metric))

    fig.update_layout(title="Preset Comparison", barmode="group")
    return fig


def create_period_comparison_chart(period_results: dict, symbol: str) -> go.Figure:
    fig = go.Figure()
    periods = list(period_results.keys())
    metrics_keys = list(next(iter(period_results.values())).keys())

    for metric in metrics_keys:
        values = [period_results[p].get(metric, 0) for p in periods]
        fig.add_trace(go.Bar(x=periods, y=values, name=metric))

    fig.update_layout(title=f"{symbol} Period Comparison", barmode="group")
    return fig
