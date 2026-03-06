"""CLI 진입점"""

import argparse

from config import CAPITAL, FeeModel, SYMBOLS_BASE


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="stock-bot 백테스트")
    parser.add_argument("--symbols", nargs="+", default=SYMBOLS_BASE[:1], help="심볼 목록")
    parser.add_argument("--portfolio", action="store_true", help="포트폴리오 모드")
    parser.add_argument("--weights", nargs="+", type=float, default=None, help="심볼별 비중")
    parser.add_argument("--rebalance", default="monthly", help="리밸런싱 주기")
    parser.add_argument("--fee-rate", type=float, default=float(FeeModel.STANDARD), help="수수료율")
    parser.add_argument("--grid-search", action="store_true", help="그리드 서치 모드")
    parser.add_argument("--capital", type=float, default=CAPITAL, help="초기 자본")
    parser.add_argument("--report", default="terminal", choices=["terminal", "html"], help="리포트 형식")
    parser.add_argument("--compare-buyhold", action="store_true", default=True, help="B&H 비교 (기본 ON)")
    parser.add_argument("--compare-presets", action="store_true", help="프리셋 비교 모드")
    parser.add_argument("--single-vs-mixed", action="store_true", help="단일 vs 혼합 비교")
    parser.add_argument("--full-report", action="store_true", help="전체 분석 파이프라인 실행")
    parser.add_argument("--periods", default="1y,3y,5y,10y,20y", help="분석 기간 (쉼표 구분)")
    parser.add_argument("--timeframes", default="daily,weekly", help="타임프레임 (쉼표 구분)")
    parser.add_argument("--output", default="full_report.html", help="출력 파일 경로")
    parser.add_argument("--top-n", type=int, default=5, help="그리드 서치 top N")
    parser.add_argument("--n-jobs", type=int, default=None, help="병렬 작업 수")
    parser.add_argument("--progress", action="store_true", help="진행률 표시")
    return parser.parse_args(argv)


def run_full_analysis(args):
    from backtest.data_loader import load_multi
    from backtest.grid_search import run_full_grid_search
    from backtest.report_html import generate_full_html_report
    from config import SYMBOLS_3X, SYMBOLS_BASE, FeeModel

    all_symbols = SYMBOLS_BASE + SYMBOLS_3X
    data = load_multi(all_symbols)

    periods = args.periods.split(",")
    timeframes = args.timeframes.split(",")
    fee_rates = [float(FeeModel.STANDARD), float(FeeModel.EVENT)]

    hourly_data = None
    if "hourly" in timeframes:
        hourly_data = load_multi(all_symbols, interval="1h")

    grid_results = run_full_grid_search(
        data=data,
        top_n=args.top_n,
        periods=periods,
        timeframes=timeframes,
        fee_rates=fee_rates,
        n_jobs=args.n_jobs,
        progress=args.progress,
        hourly_data=hourly_data,
    )

    # Build symbol_data for report
    symbol_data = {}
    for sym, df in data.items():
        symbol_data[sym] = {"ohlcv": df, "trades": [], "equity_curve": df["close"]}

    output_path = generate_full_html_report(
        grid_results=grid_results,
        symbol_data=symbol_data,
        output_path=args.output,
    )
    print(f"Report generated: {output_path}")


def main(argv=None):
    args = parse_args(argv)

    if args.full_report:
        run_full_analysis(args)
        return

    from backtest.data_loader import load_multi, load_single
    from backtest.strategies.bb_rsi_ema import BbRsiEma

    strategy = BbRsiEma()

    if args.grid_search:
        from backtest.grid_search import run_grid_search
        from backtest.report import print_grid_results

        df = load_single(args.symbols[0])
        results = run_grid_search(df, capital=args.capital, fee_rate=args.fee_rate)
        print_grid_results(results)
        return

    if args.compare_presets:
        from backtest.comparisons import PRESETS, run_preset_comparison
        from backtest.report import print_preset_comparison

        all_symbols = set()
        for w in PRESETS.values():
            all_symbols.update(w.keys())
        data = load_multi(list(all_symbols))
        results = run_preset_comparison(data, strategy, capital=args.capital, fee_rate=args.fee_rate)
        print_preset_comparison(results)
        return

    if args.single_vs_mixed:
        from backtest.comparisons import run_single_vs_portfolio
        from config import PRESET_MIXED

        data = load_multi(list(PRESET_MIXED.keys()))
        results = run_single_vs_portfolio(data, strategy, PRESET_MIXED, capital=args.capital)
        print(results)
        return

    if args.portfolio:
        from backtest.engine import run_portfolio_backtest
        from backtest.metrics import compute_metrics
        from backtest.report import print_summary

        data = load_multi(args.symbols)
        weights = None
        if args.weights:
            weights = dict(zip(args.symbols, args.weights))
        result = run_portfolio_backtest(
            data, strategy, capital=args.capital, fee_rate=args.fee_rate,
            weights=weights, rebalance_freq=args.rebalance,
        )
        metrics = compute_metrics(result["equity_curve"], total_trades=result["total_trades"])
        print_summary(metrics)
    else:
        from backtest.buyhold import compare_vs_buyhold, compute_buyhold
        from backtest.engine import run_backtest
        from backtest.metrics import compute_metrics
        from backtest.report import print_summary, print_vs_buyhold

        df = load_single(args.symbols[0])
        result = run_backtest(df, strategy, capital=args.capital, fee_rate=args.fee_rate)
        metrics = compute_metrics(result["equity_curve"], total_trades=result["total_trades"])
        print_summary(metrics)

        if args.compare_buyhold:
            bh = compute_buyhold(df, capital=args.capital, fee_rate=args.fee_rate)
            comp = compare_vs_buyhold(
                {"total_return": metrics["total_return"]}, bh
            )
            print_vs_buyhold(comp)

    if args.report == "html":
        from backtest.report import generate_html_report

        html = generate_html_report(metrics)
        with open("backtest_report.html", "w") as f:
            f.write(html)
        print("\nHTML report saved to backtest_report.html")


if __name__ == "__main__":
    main()
