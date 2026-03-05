"""터미널 + HTML 리포트"""


def print_summary(metrics: dict) -> None:
    print("=" * 50)
    print("백테스트 결과 요약")
    print("=" * 50)
    print(f"  총 수익률:      {metrics.get('total_return', 0):.2%}")
    print(f"  연간 수익률:    {metrics.get('annualized_return', 0):.2%}")
    print(f"  최대 낙폭:      {metrics.get('max_drawdown', 0):.2%}")
    print(f"  Sharpe Ratio:   {metrics.get('sharpe_ratio', 0):.4f}")
    print(f"  Calmar Ratio:   {metrics.get('calmar_ratio', 0):.4f}")
    print(f"  거래 횟수:      {metrics.get('total_trades', 0)}")
    print("=" * 50)


def print_vs_buyhold(comparison: dict) -> None:
    print("\n[ Strategy vs Buy & Hold ]")
    print(f"  전략 수익률:    {comparison.get('strategy_return', 0):.2%}")
    print(f"  B&H 수익률:     {comparison.get('buyhold_return', 0):.2%}")
    print(f"  초과 수익률:    {comparison.get('excess_return', 0):.2%}")


def print_preset_comparison(results: dict) -> None:
    print("\n[ 프리셋 포트폴리오 비교 ]")
    print(f"{'프리셋':<12} {'수익률':>10} {'MDD':>10} {'Sharpe':>10} {'거래횟수':>10}")
    print("-" * 54)
    for name, m in results.items():
        print(
            f"{name:<12} "
            f"{m.get('total_return', 0):>9.2%} "
            f"{m.get('max_drawdown', 0):>9.2%} "
            f"{m.get('sharpe_ratio', 0):>9.4f} "
            f"{m.get('total_trades', 0):>10}"
        )


def print_grid_results(results: list[dict], top_n: int = 10) -> None:
    print(f"\n[ 그리드 서치 상위 {top_n}개 ]")
    for i, r in enumerate(results[:top_n]):
        print(f"  #{i+1}: Sharpe={r.get('sharpe_ratio', 0):.4f} "
              f"거래={r.get('total_trades', 0)} "
              f"초과={r.get('vs_buyhold_excess', 0):.2%} "
              f"params={r.get('params', {})}")


def generate_html_report(
    metrics: dict,
    comparison: dict | None = None,
    preset_results: dict | None = None,
) -> str:
    html = ["<html><head><title>Backtest Report</title></head><body>"]
    html.append("<h1>Backtest Report</h1>")

    html.append("<h2>Summary</h2>")
    html.append("<table border='1'>")
    for key, val in metrics.items():
        if key == "total_trades":
            html.append(f"<tr><td>{key}</td><td>{val}</td></tr>")
        elif isinstance(val, float):
            html.append(f"<tr><td>{key}</td><td>{val:.4f}</td></tr>")
        else:
            html.append(f"<tr><td>{key}</td><td>{val}</td></tr>")
    html.append("</table>")

    if comparison:
        html.append("<h2>vs Buy & Hold</h2>")
        html.append(f"<p>Excess Return: {comparison.get('excess_return', 0):.2%}</p>")

    if preset_results:
        html.append("<h2>Preset Comparison</h2>")
        html.append("<table border='1'>")
        html.append("<tr><th>Preset</th><th>Return</th><th>MDD</th><th>Sharpe</th><th>Trades</th></tr>")
        for name, m in preset_results.items():
            html.append(
                f"<tr><td>{name}</td>"
                f"<td>{m.get('total_return', 0):.2%}</td>"
                f"<td>{m.get('max_drawdown', 0):.2%}</td>"
                f"<td>{m.get('sharpe_ratio', 0):.4f}</td>"
                f"<td>{m.get('total_trades', 0)}</td></tr>"
            )
        html.append("</table>")

    html.append("</body></html>")
    return "\n".join(html)
