"""Phase 5 Step 1: report.py TC"""

from backtest.report import (
    generate_html_report,
    print_grid_results,
    print_preset_comparison,
    print_summary,
    print_vs_buyhold,
)


SAMPLE_METRICS = {
    "total_return": 0.25,
    "annualized_return": 0.12,
    "max_drawdown": -0.15,
    "sharpe_ratio": 1.5,
    "calmar_ratio": 0.8,
    "total_trades": 42,
}


# ── TC-1: print_summary ──
def test_print_summary(capsys):
    print_summary(SAMPLE_METRICS)
    out = capsys.readouterr().out
    assert "42" in out  # 거래 횟수


# ── TC-2: print_vs_buyhold ──
def test_print_vs_buyhold(capsys):
    comparison = {"strategy_return": 0.25, "buyhold_return": 0.15, "excess_return": 0.10}
    print_vs_buyhold(comparison)
    out = capsys.readouterr().out
    assert "10.00%" in out


# ── TC-3: print_preset_comparison ──
def test_print_preset_comparison(capsys):
    results = {
        "growth": {"total_return": 0.3, "max_drawdown": -0.2, "sharpe_ratio": 1.2, "total_trades": 30},
    }
    print_preset_comparison(results)
    out = capsys.readouterr().out
    assert "growth" in out


# ── TC-4: print_grid_results ──
def test_print_grid_results(capsys):
    results = [{"sharpe_ratio": 1.5, "total_trades": 10, "vs_buyhold_excess": 0.05, "params": {"a": 1}}]
    print_grid_results(results, top_n=1)
    out = capsys.readouterr().out
    assert "#1" in out


# ── TC-5: generate_html_report ──
def test_generate_html_report():
    html = generate_html_report(SAMPLE_METRICS)
    assert isinstance(html, str)
    assert "<html>" in html
    assert "Backtest Report" in html


# ── TC-6: HTML에 거래 횟수 포함 ──
def test_html_has_total_trades():
    html = generate_html_report(SAMPLE_METRICS)
    assert "total_trades" in html
    assert "42" in html
