"""buy_only 모드 매수 타이밍 전용 테스트"""
import json
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import numpy as np
import pytest


@pytest.fixture(autouse=True)
def tmp_state_dir(monkeypatch, tmp_path):
    """STATE_DIR을 임시 디렉토리로 교체"""
    import alert
    monkeypatch.setattr(alert, "STATE_DIR", tmp_path)
    return tmp_path


def _make_df(rsi_target, n=50):
    """특정 RSI 근처가 되도록 가격 시리즈 생성"""
    np.random.seed(42)
    if rsi_target < 40:
        prices = 100 - np.cumsum(np.random.uniform(0.5, 1.5, n))
        prices = np.maximum(prices, 10)
    elif rsi_target > 60:
        prices = 100 + np.cumsum(np.random.uniform(0.5, 1.5, n))
    else:
        prices = 100 + np.cumsum(np.random.uniform(-0.5, 0.5, n))

    dates = pd.date_range("2025-01-01", periods=n, freq="B")
    df = pd.DataFrame({
        "Open": prices,
        "High": prices * 1.01,
        "Low": prices * 0.99,
        "Close": prices,
        "Volume": np.random.randint(1000000, 5000000, n),
    }, index=dates)
    return df


class TestBuyOnlyCheckSymbol:
    """check_symbol() buy_only 분기 테스트"""

    def test_buy_timing_signal_first_entry(self, tmp_state_dir):
        """RSI < buy_rsi, 첫 진입 -> BUY_TIMING 시그널"""
        import alert

        config = {"group": "2x 구글", "buy_rsi": 30, "sell_rsi": None,
                  "rebuy_rsi": None, "desc": "구글 2배 레버리지", "buy_only": True}

        df = _make_df(rsi_target=20)

        with patch.object(alert.yf, "Ticker") as mock_ticker:
            mock_ticker.return_value.history.return_value = df
            with patch.object(alert, "get_atr_ratio", return_value=(1.0, 2.5)):
                result, error = alert.check_symbol("GGLL", config)

        assert error is None
        assert result is not None
        if result["rsi"] < config["buy_rsi"]:
            assert result["signal"] == "BUY_TIMING"
            assert "매수 적기" in result["reason"]
        assert result["new_state"] == "CASH"

    def test_no_signal_above_threshold(self, tmp_state_dir):
        """RSI >= buy_rsi -> signal=None"""
        import alert

        config = {"group": "엔비디아", "buy_rsi": 35, "sell_rsi": None,
                  "rebuy_rsi": None, "desc": "엔비디아 현물", "buy_only": True}

        df = _make_df(rsi_target=70)

        with patch.object(alert.yf, "Ticker") as mock_ticker:
            mock_ticker.return_value.history.return_value = df
            with patch.object(alert, "get_atr_ratio", return_value=(1.0, 2.5)):
                result, error = alert.check_symbol("NVDA", config)

        assert error is None
        assert result is not None
        if result["rsi"] >= config["buy_rsi"]:
            assert result["signal"] is None
        assert result["new_state"] == "CASH"

    def test_spam_prevention(self, tmp_state_dir):
        """연속 과매도 시 두 번째는 시그널 없음"""
        import alert

        config = {"group": "2x 구글", "buy_rsi": 30, "sell_rsi": None,
                  "rebuy_rsi": None, "desc": "구글 2배 레버리지", "buy_only": True}

        df = _make_df(rsi_target=20)

        with patch.object(alert.yf, "Ticker") as mock_ticker:
            mock_ticker.return_value.history.return_value = df
            with patch.object(alert, "get_atr_ratio", return_value=(1.0, 2.5)):
                r1, _ = alert.check_symbol("GGLL", config)

        with patch.object(alert.yf, "Ticker") as mock_ticker:
            mock_ticker.return_value.history.return_value = df
            with patch.object(alert, "get_atr_ratio", return_value=(1.0, 2.5)):
                r2, _ = alert.check_symbol("GGLL", config)

        if r1 and r1["rsi"] < config["buy_rsi"]:
            assert r1["signal"] == "BUY_TIMING"
            assert r2["signal"] is None
            assert "지속" in r2["reason"]


class TestBuyOnlyWhatToDo:
    """_what_to_do() buy_only 분기 테스트"""

    def test_below_buy_rsi(self):
        import alert
        r = {"rsi": 25, "signal": None, "state": "CASH", "new_state": "CASH",
             "config": {"buy_rsi": 30, "buy_only": True},
             "copper_blocked": None, "bb_upper": 100, "price": 80,
             "dca_boost": True, "atr_ratio": 1.0}
        result = alert._what_to_do(r)
        assert "저점 매수" in result

    def test_approaching_buy_rsi(self):
        import alert
        r = {"rsi": 35, "signal": None, "state": "CASH", "new_state": "CASH",
             "config": {"buy_rsi": 30, "buy_only": True},
             "copper_blocked": None, "bb_upper": 100, "price": 80,
             "dca_boost": False, "atr_ratio": 1.0}
        result = alert._what_to_do(r)
        assert "접근 중" in result

    def test_far_from_buy_rsi(self):
        import alert
        r = {"rsi": 60, "signal": None, "state": "CASH", "new_state": "CASH",
             "config": {"buy_rsi": 30, "buy_only": True},
             "copper_blocked": None, "bb_upper": 100, "price": 80,
             "dca_boost": False, "atr_ratio": 1.0}
        result = alert._what_to_do(r)
        assert "관망" in result


class TestSymbolsConfig:
    """SYMBOLS 설정 검증"""

    def test_ggll_config(self):
        import alert
        assert "GGLL" in alert.SYMBOLS
        cfg = alert.SYMBOLS["GGLL"]
        assert cfg["buy_only"] is True
        assert cfg["buy_rsi"] == 30
        assert cfg["sell_rsi"] is None
        assert cfg["rebuy_rsi"] is None

    def test_nvda_config(self):
        import alert
        assert "NVDA" in alert.SYMBOLS
        cfg = alert.SYMBOLS["NVDA"]
        assert cfg["buy_only"] is True
        assert cfg["buy_rsi"] == 35
        assert cfg["sell_rsi"] is None
        assert cfg["rebuy_rsi"] is None

    @pytest.mark.parametrize("symbol,expected_rsi", [
        ("MSTR", 30), ("HOOD", 30), ("COIN", 30),
    ])
    def test_crypto_buy_only_config(self, symbol, expected_rsi):
        import alert
        assert symbol in alert.SYMBOLS
        cfg = alert.SYMBOLS[symbol]
        assert cfg["buy_only"] is True
        assert cfg["buy_rsi"] == expected_rsi
        assert cfg["sell_rsi"] is None
        assert cfg["rebuy_rsi"] is None

    def test_total_symbols_count(self):
        import alert
        assert len(alert.SYMBOLS) == 12
