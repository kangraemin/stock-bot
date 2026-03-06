"""bot_listener.py 테스트"""
from unittest.mock import patch, MagicMock
import pandas as pd
import numpy as np
import pytest


@pytest.fixture(autouse=True)
def tmp_state_dir(monkeypatch, tmp_path):
    import alert
    monkeypatch.setattr(alert, "STATE_DIR", tmp_path)
    return tmp_path


def _make_df(n=50):
    np.random.seed(42)
    prices = 100 + np.cumsum(np.random.uniform(-0.5, 0.5, n))
    dates = pd.date_range("2025-01-01", periods=n, freq="B")
    return pd.DataFrame({
        "Open": prices, "High": prices * 1.01,
        "Low": prices * 0.99, "Close": prices,
        "Volume": np.random.randint(1000000, 5000000, n),
    }, index=dates)


class TestBuildStatus:
    def test_all_symbols(self):
        import bot_listener
        import alert

        df = _make_df()
        with patch.object(alert.yf, "Ticker") as mock_ticker:
            mock_ticker.return_value.history.return_value = df
            with patch.object(alert, "get_atr_ratio", return_value=(1.0, 2.5)):
                with patch.object(alert, "get_copper_trend", return_value=("up", 4.5, 4.3)):
                    with patch.object(alert, "get_vix_term", return_value=("contango", 0.9, 15.0)):
                        result = bot_listener.build_status()

        for sym in alert.SYMBOLS:
            assert sym in result

    def test_single_symbol(self):
        import bot_listener
        import alert

        df = _make_df()
        with patch.object(alert.yf, "Ticker") as mock_ticker:
            mock_ticker.return_value.history.return_value = df
            with patch.object(alert, "get_atr_ratio", return_value=(1.0, 2.5)):
                with patch.object(alert, "get_copper_trend", return_value=("up", 4.5, 4.3)):
                    with patch.object(alert, "get_vix_term", return_value=("contango", 0.9, 15.0)):
                        result = bot_listener.build_status("SOXL")

        assert "SOXL" in result
        assert "RSI" in result

    def test_invalid_symbol(self):
        import bot_listener
        result = bot_listener.build_status("INVALID")
        assert "알 수 없는 종목" in result

    def test_build_help(self):
        import bot_listener
        result = bot_listener.build_help()
        assert "/status" in result
        assert "/help" in result


class TestHandleMessage:
    def test_status_calls_send(self):
        import bot_listener
        import alert

        df = _make_df()
        msg = {"text": "/status", "chat": {"id": "123"}}

        with patch.object(bot_listener, "send_reply") as mock_send:
            with patch.object(bot_listener, "ALLOWED_CHAT_ID", "123"):
                with patch.object(alert.yf, "Ticker") as mock_ticker:
                    mock_ticker.return_value.history.return_value = df
                    with patch.object(alert, "get_atr_ratio", return_value=(1.0, 2.5)):
                        with patch.object(alert, "get_copper_trend", return_value=("up", 4.5, 4.3)):
                            with patch.object(alert, "get_vix_term", return_value=("contango", 0.9, 15.0)):
                                bot_listener.handle_message(msg)

        mock_send.assert_called_once()

    def test_unknown_command_ignored(self):
        import bot_listener

        msg = {"text": "hello", "chat": {"id": "123"}}
        with patch.object(bot_listener, "send_reply") as mock_send:
            with patch.object(bot_listener, "ALLOWED_CHAT_ID", "123"):
                bot_listener.handle_message(msg)

        mock_send.assert_not_called()

    def test_wrong_chat_id_ignored(self):
        import bot_listener

        msg = {"text": "/status", "chat": {"id": "999"}}
        with patch.object(bot_listener, "send_reply") as mock_send:
            with patch.object(bot_listener, "ALLOWED_CHAT_ID", "123"):
                bot_listener.handle_message(msg)

        mock_send.assert_not_called()
