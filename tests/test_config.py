"""Phase 1 Step 1: config.py TC"""
import pathlib

import pytest


ROOT = pathlib.Path(__file__).resolve().parent.parent


class TestSymbols:
    """TC-01, TC-02"""

    def test_symbols_base_count(self):
        from config import SYMBOLS_BASE
        assert len(SYMBOLS_BASE) == 8

    def test_symbols_base_members(self):
        from config import SYMBOLS_BASE
        expected = {"SPY", "QQQ", "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "TSLA"}
        assert set(SYMBOLS_BASE) == expected

    def test_symbols_3x_count(self):
        from config import SYMBOLS_3X
        assert len(SYMBOLS_3X) == 5

    def test_symbols_3x_members(self):
        from config import SYMBOLS_3X
        expected = {"TQQQ", "SPXL", "SOXL", "UPRO", "TECL"}
        assert set(SYMBOLS_3X) == expected


class TestLeverageMap:
    """TC-03, TC-04"""

    def test_keys_match_symbols_3x(self):
        from config import LEVERAGE_MAP, SYMBOLS_3X
        assert set(LEVERAGE_MAP.keys()) == set(SYMBOLS_3X)

    def test_known_mappings(self):
        from config import LEVERAGE_MAP
        assert LEVERAGE_MAP["TQQQ"] == "QQQ"
        assert LEVERAGE_MAP["SPXL"] == "SPY"
        assert LEVERAGE_MAP["UPRO"] == "SPY"


class TestFeeModel:
    """TC-05, TC-06"""

    def test_standard_fee(self):
        from config import FeeModel
        assert FeeModel.STANDARD == pytest.approx(0.0025)

    def test_event_fee(self):
        from config import FeeModel
        assert FeeModel.EVENT == pytest.approx(0.0009)


class TestDefaults:
    """TC-07, TC-08"""

    def test_slippage(self):
        from config import SLIPPAGE
        assert SLIPPAGE == pytest.approx(0.001)

    def test_capital(self):
        from config import CAPITAL
        assert CAPITAL == 2000


class TestPresets:
    """TC-09 ~ TC-12"""

    def test_preset_growth(self):
        from config import PRESET_GROWTH
        expected = {"TQQQ", "TECL", "SOXL", "NVDA", "TSLA"}
        symbols = set(PRESET_GROWTH.keys()) if isinstance(PRESET_GROWTH, dict) else set(PRESET_GROWTH)
        assert symbols == expected

    def test_preset_safe(self):
        from config import PRESET_SAFE
        expected = {"SPY", "MSFT", "GOOGL", "AAPL"}
        symbols = set(PRESET_SAFE.keys()) if isinstance(PRESET_SAFE, dict) else set(PRESET_SAFE)
        assert symbols == expected

    def test_preset_mixed_weights_sum(self):
        from config import PRESET_MIXED
        assert isinstance(PRESET_MIXED, dict)
        assert sum(PRESET_MIXED.values()) == pytest.approx(1.0)
        expected_symbols = {"TQQQ", "SPXL", "SPY", "MSFT", "AAPL"}
        assert set(PRESET_MIXED.keys()) == expected_symbols

    def test_preset_mixed_specific_weights(self):
        from config import PRESET_MIXED
        assert PRESET_MIXED["TQQQ"] == pytest.approx(0.30)
        assert PRESET_MIXED["SPXL"] == pytest.approx(0.20)
        assert PRESET_MIXED["SPY"] == pytest.approx(0.20)
        assert PRESET_MIXED["MSFT"] == pytest.approx(0.15)
        assert PRESET_MIXED["AAPL"] == pytest.approx(0.15)

    def test_preset_all_3x(self):
        from config import PRESET_ALL_3X, SYMBOLS_3X
        assert isinstance(PRESET_ALL_3X, dict)
        assert set(PRESET_ALL_3X.keys()) == set(SYMBOLS_3X)
        weights = list(PRESET_ALL_3X.values())
        assert all(w == pytest.approx(weights[0]) for w in weights), "균등 배분이어야 함"
        assert sum(weights) == pytest.approx(1.0)


class TestProjectFiles:
    """TC-13, TC-14"""

    def test_requirements_txt_exists(self):
        req = ROOT / "requirements.txt"
        assert req.exists(), "requirements.txt 없음"

    def test_requirements_packages(self):
        req = ROOT / "requirements.txt"
        content = req.read_text()
        for pkg in ["yfinance", "pandas", "numpy", "ta", "matplotlib", "pyarrow", "pytest"]:
            assert pkg in content, f"{pkg} 누락"

    def test_gitignore_exists(self):
        gi = ROOT / ".gitignore"
        assert gi.exists(), ".gitignore 없음"

    def test_gitignore_patterns(self):
        gi = ROOT / ".gitignore"
        content = gi.read_text()
        for pattern in ["data/", "__pycache__", ".venv", "backtest/output/"]:
            assert pattern in content, f"{pattern} 누락"
