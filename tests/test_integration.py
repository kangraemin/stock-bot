"""Phase 6 Step 1: 통합 테스트"""

import numpy as np
import pandas as pd
import pytest


# ── TC-1: 전체 모듈 import 검증 ──
def test_all_imports():
    import backtest
    import backtest.buyhold
    import backtest.comparisons
    import backtest.data_loader
    import backtest.engine
    import backtest.grid_search
    import backtest.metrics
    import backtest.portfolio
    import backtest.rebalancer
    import backtest.report
    import backtest.runner
    import backtest.strategies
    import backtest.strategies.base
    import backtest.strategies.bb_rsi_ema


@pytest.fixture()
def sample_data(tmp_path):
    """200일 멀티 심볼 테스트 데이터"""
    dates = pd.date_range("2022-01-03", periods=200, freq="B")
    rng = np.random.default_rng(42)
    data = {}
    for sym in ("SPY", "QQQ"):
        close = 100 + rng.standard_normal(200).cumsum()
        df = pd.DataFrame(
            {
                "open": close + rng.uniform(-0.5, 0.5, 200),
                "high": close + rng.uniform(0, 1, 200),
                "low": close - rng.uniform(0, 1, 200),
                "close": close,
                "volume": rng.integers(1_000_000, 10_000_000, 200),
            },
            index=dates,
        )
        df.index.name = "Date"
        df.to_parquet(tmp_path / f"{sym}.parquet")
        data[sym] = df
    return tmp_path, data


# ── TC-2: 엔드투엔드 단일 종목 ──
def test_e2e_single(sample_data):
    tmp_path, _ = sample_data

    from backtest.buyhold import compare_vs_buyhold, compute_buyhold
    from backtest.data_loader import load_single
    from backtest.engine import run_backtest
    from backtest.metrics import compute_metrics
    from backtest.report import print_summary
    from backtest.strategies.bb_rsi_ema import BbRsiEma

    df = load_single("SPY", data_dir=tmp_path)
    strategy = BbRsiEma()
    result = run_backtest(df, strategy)
    metrics = compute_metrics(result["equity_curve"], total_trades=result["total_trades"])

    assert "total_return" in metrics
    assert "total_trades" in metrics
    assert isinstance(metrics["total_trades"], int)

    bh = compute_buyhold(df)
    comp = compare_vs_buyhold({"total_return": metrics["total_return"]}, bh)
    assert "excess_return" in comp


# ── TC-3: 엔드투엔드 포트폴리오 ──
def test_e2e_portfolio(sample_data):
    tmp_path, _ = sample_data

    from backtest.data_loader import load_multi
    from backtest.engine import run_portfolio_backtest
    from backtest.metrics import compute_metrics
    from backtest.strategies.bb_rsi_ema import BbRsiEma

    data = load_multi(["SPY", "QQQ"], data_dir=tmp_path)
    strategy = BbRsiEma()
    result = run_portfolio_backtest(data, strategy)
    metrics = compute_metrics(result["equity_curve"], total_trades=result["total_trades"])

    assert metrics["total_trades"] >= 0
    assert "max_drawdown" in metrics
    assert "sharpe_ratio" in metrics
