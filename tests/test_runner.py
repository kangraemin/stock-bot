"""Phase 5 Step 2: runner.py CLI TC"""

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
