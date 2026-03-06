"""Plotly 기반 인터랙티브 차트 생성"""

from html import escape

import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio


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


def create_grid_results_table(grid_results: list[dict]) -> str:
    if not grid_results:
        return "<table></table>"

    rows = []
    rows.append("<table border='1' cellpadding='4' cellspacing='0'>")
    rows.append("<tr><th>#</th><th>params</th><th>total_return</th>"
                "<th>sharpe_ratio</th><th>max_drawdown</th><th>total_trades</th></tr>")

    for i, r in enumerate(grid_results, 1):
        params_str = ", ".join(f"{k}={v}" for k, v in r.get("params", {}).items())
        rows.append(
            f"<tr><td>{i}</td>"
            f"<td>{escape(params_str)}</td>"
            f"<td>{r.get('total_return', 0):.4f}</td>"
            f"<td>{r.get('sharpe_ratio', 0):.4f}</td>"
            f"<td>{r.get('max_drawdown', 0):.4f}</td>"
            f"<td>{r.get('total_trades', 0)}</td></tr>"
        )

    rows.append("</table>")
    return "\n".join(rows)


def generate_full_html_report(
    symbol_data: dict,
    grid_results: list[dict] | None = None,
    preset_results: dict | None = None,
    output_path: str = "full_report.html",
) -> str:
    parts = []
    parts.append("<!DOCTYPE html><html><head><title>Full Grid Analysis Report</title>")
    parts.append('<script src="https://cdn.plot.ly/plotly-latest.min.js"></script>')
    parts.append("</head><body>")
    parts.append("<h1>Full Grid Analysis Report</h1>")

    # Navigation
    parts.append("<nav>")
    for symbol in symbol_data:
        parts.append(f'<a href="#{symbol}">{symbol}</a> | ')
    parts.append("</nav><hr>")

    # Symbol sections
    for symbol, sdata in symbol_data.items():
        parts.append(f'<div id="{symbol}">')
        parts.append(f"<h2>{symbol}</h2>")

        fig = create_symbol_chart(
            sdata["ohlcv"],
            sdata.get("trades", []),
            sdata.get("equity_curve", pd.Series(dtype=float)),
            symbol,
            bh_curve=sdata.get("bh_curve"),
        )
        parts.append(pio.to_html(fig, include_plotlyjs=False, full_html=False))
        parts.append("</div>")

    # Grid results table
    if grid_results:
        parts.append("<h2>Grid Search Top Results</h2>")
        if isinstance(grid_results, dict):
            for sym, tf_data in grid_results.items():
                for tf, period_data in tf_data.items():
                    for period, fee_data in period_data.items():
                        for fee_label, results_list in fee_data.items():
                            parts.append(f"<h3>{sym} | {tf} | {period} | {fee_label}</h3>")
                            parts.append(create_grid_results_table(results_list))
        else:
            parts.append(create_grid_results_table(grid_results))

    # Preset comparison
    if preset_results:
        parts.append("<h2>Preset Comparison</h2>")
        fig = create_preset_comparison_chart(preset_results)
        parts.append(pio.to_html(fig, include_plotlyjs=False, full_html=False))

    parts.append("</body></html>")

    html_content = "\n".join(parts)
    with open(output_path, "w") as f:
        f.write(html_content)

    return output_path
