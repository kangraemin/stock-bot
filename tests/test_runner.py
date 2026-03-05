"""Phase 5 Step 2 + Phase 4 Step 1: runner.py CLI TC"""

from backtest.runner import parse_args
from config import CAPITAL, FeeModel


# ── TC-1: parse_args 기본값 ──
def test_parse_args_defaults():
    args = parse_args([])
    assert args.capital == CAPITAL
    assert args.fee_rate == float(FeeModel.STANDARD)


# ── TC-2: --symbols 파싱 ──
def test_parse_symbols():
    args = parse_args(["--symbols", "SPY", "QQQ"])
    assert args.symbols == ["SPY", "QQQ"]


# ── TC-3: --portfolio 플래그 ──
def test_portfolio_flag():
    args = parse_args(["--portfolio"])
    assert args.portfolio is True
    args2 = parse_args([])
    assert args2.portfolio is False


# ── TC-4: --grid-search 플래그 ──
def test_grid_search_flag():
    args = parse_args(["--grid-search"])
    assert args.grid_search is True


# ── TC-5: --compare-presets 플래그 ──
def test_compare_presets_flag():
    args = parse_args(["--compare-presets"])
    assert args.compare_presets is True


# ── TC-6: --single-vs-mixed 플래그 ──
def test_single_vs_mixed_flag():
    args = parse_args(["--single-vs-mixed"])
    assert args.single_vs_mixed is True


# ── TC-7: --capital 파싱 ──
def test_capital_parsing():
    args = parse_args(["--capital", "5000"])
    assert args.capital == 5000.0


# ── TC-8: --fee-rate 파싱 ──
def test_fee_rate_parsing():
    args = parse_args(["--fee-rate", "0.001"])
    assert args.fee_rate == 0.001


# ============================================================
# Phase 4 Step 1: --full-report CLI 통합 테스트
# ============================================================

# --- TC-9: --full-report 플래그 파싱 ---
def test_full_report_flag():
    args = parse_args(["--full-report"])
    assert args.full_report is True
    args2 = parse_args([])
    assert args2.full_report is False


# --- TC-10: --periods 파라미터 기본값 ---
def test_periods_default():
    args = parse_args(["--full-report"])
    assert hasattr(args, "periods")
    assert "1y" in args.periods.lower() or "1Y" in args.periods


# --- TC-11: --timeframes 파라미터 기본값 ---
def test_timeframes_default():
    args = parse_args(["--full-report"])
    assert hasattr(args, "timeframes")
    assert "daily" in args.timeframes.lower()


# --- TC-12: --output 파라미터 기본값 ---
def test_output_default():
    args = parse_args(["--full-report"])
    assert hasattr(args, "output")
    assert "full_report" in args.output or "html" in args.output


# --- TC-13: --top-n 파라미터 기본값 ---
def test_top_n_default():
    args = parse_args(["--full-report"])
    assert hasattr(args, "top_n")
    assert args.top_n == 5


# --- TC-14: --n-jobs 파라미터 ---
def test_n_jobs_parsing():
    args = parse_args(["--full-report", "--n-jobs", "4"])
    assert args.n_jobs == 4


# --- TC-15: run_full_analysis 함수 존재 ---
def test_run_full_analysis_exists():
    from backtest.runner import run_full_analysis  # noqa: F401
    assert callable(run_full_analysis)
