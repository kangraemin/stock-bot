"""Phase 1 Step 2: download.py TC"""
import os
import pathlib
import time
from unittest.mock import patch, MagicMock

import pandas as pd
import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"


@pytest.fixture
def mock_yf_download():
    """yfinance.download를 mock하여 네트워크 호출 방지"""
    dates = pd.date_range("2024-01-02", periods=5, freq="B")
    df = pd.DataFrame(
        {
            "Open": [100.0, 101, 102, 103, 104],
            "High": [105.0, 106, 107, 108, 109],
            "Low": [99.0, 100, 101, 102, 103],
            "Close": [104.0, 105, 106, 107, 108],
            "Volume": [1000, 1100, 1200, 1300, 1400],
        },
        index=dates,
    )
    with patch("yfinance.download", return_value=df) as mock_dl:
        yield mock_dl


@pytest.fixture
def tmp_data_dir(tmp_path, monkeypatch):
    """data/ 대신 임시 디렉토리 사용"""
    monkeypatch.setattr("download.DATA_DIR", tmp_path)
    return tmp_path


class TestDownloadFunction:
    """TC-01, TC-02, TC-03, TC-04"""

    def test_download_symbol_exists(self):
        from download import download_symbol
        assert callable(download_symbol)

    def test_creates_parquet(self, mock_yf_download, tmp_data_dir):
        from download import download_symbol
        download_symbol("SPY", data_dir=tmp_data_dir)
        assert (tmp_data_dir / "SPY.parquet").exists()

    def test_columns_normalized(self, mock_yf_download, tmp_data_dir):
        from download import download_symbol
        download_symbol("SPY", data_dir=tmp_data_dir)
        df = pd.read_parquet(tmp_data_dir / "SPY.parquet")
        for col in ["open", "high", "low", "close", "volume"]:
            assert col in df.columns, f"{col} 컬럼 누락"

    def test_datetime_index(self, mock_yf_download, tmp_data_dir):
        from download import download_symbol
        download_symbol("SPY", data_dir=tmp_data_dir)
        df = pd.read_parquet(tmp_data_dir / "SPY.parquet")
        assert isinstance(df.index, pd.DatetimeIndex)


class TestCache:
    """TC-05, TC-06"""

    def test_skip_if_recent(self, mock_yf_download, tmp_data_dir):
        from download import download_symbol
        # 첫 번째 다운로드
        download_symbol("SPY", data_dir=tmp_data_dir)
        assert mock_yf_download.call_count == 1
        # 두 번째 호출 - 캐시로 스킵
        download_symbol("SPY", data_dir=tmp_data_dir)
        assert mock_yf_download.call_count == 1, "캐시된 파일은 재다운로드하면 안 됨"

    def test_force_redownload(self, mock_yf_download, tmp_data_dir):
        from download import download_symbol
        download_symbol("SPY", data_dir=tmp_data_dir)
        download_symbol("SPY", data_dir=tmp_data_dir, force=True)
        assert mock_yf_download.call_count == 2, "force=True면 재다운로드해야 함"


class TestCLI:
    """TC-07, TC-08, TC-09"""

    def test_parse_symbols(self):
        from download import parse_args
        args = parse_args(["--symbols", "SPY", "QQQ"])
        assert "SPY" in args.symbols
        assert "QQQ" in args.symbols

    def test_parse_period_default(self):
        from download import parse_args
        args = parse_args([])
        assert hasattr(args, "period")
        assert args.period is not None

    def test_parse_period_custom(self):
        from download import parse_args
        args = parse_args(["--period", "1y"])
        assert args.period == "1y"

    def test_parse_force(self):
        from download import parse_args
        args = parse_args(["--force"])
        assert args.force is True


class TestDefaults:
    """TC-10, TC-11, TC-12"""

    def test_default_symbols_count(self):
        from download import DEFAULT_SYMBOLS
        # SYMBOLS_BASE(8) + SYMBOLS_3X(5) + 기초자산(SOXX, XLK 등) >= 13
        assert len(DEFAULT_SYMBOLS) >= 13

    def test_data_dir_auto_create(self, mock_yf_download, tmp_path):
        from download import download_symbol
        new_dir = tmp_path / "subdir"
        assert not new_dir.exists()
        download_symbol("SPY", data_dir=new_dir)
        assert new_dir.exists()

    def test_invalid_symbol_no_crash(self, tmp_data_dir):
        """잘못된 심볼이어도 예외 없이 처리"""
        from download import download_symbol
        with patch("yfinance.download", return_value=pd.DataFrame()):
            # 빈 DataFrame 반환 시 크래시하면 안 됨
            download_symbol("INVALID_XYZ_999", data_dir=tmp_data_dir)


class TestInterval:
    """시간봉(1h) interval 지원 테스트"""

    def test_interval_param_exists(self):
        """download_symbol에 interval 파라미터 존재"""
        import inspect
        from download import download_symbol
        sig = inspect.signature(download_symbol)
        assert "interval" in sig.parameters

    def test_hourly_filename(self, mock_yf_download, tmp_data_dir):
        """interval='1h' 시 SPY_1h.parquet 파일명"""
        from download import download_symbol
        download_symbol("SPY", data_dir=tmp_data_dir, interval="1h")
        assert (tmp_data_dir / "SPY_1h.parquet").exists()
        assert not (tmp_data_dir / "SPY.parquet").exists()

    def test_daily_filename_unchanged(self, mock_yf_download, tmp_data_dir):
        """interval='1d' (기본값) 시 기존 SPY.parquet 유지"""
        from download import download_symbol
        download_symbol("SPY", data_dir=tmp_data_dir, interval="1d")
        assert (tmp_data_dir / "SPY.parquet").exists()

    def test_hourly_passes_interval_to_yfinance(self, mock_yf_download, tmp_data_dir):
        """interval='1h' 시 yfinance.download에 interval='1h' 전달"""
        from download import download_symbol
        download_symbol("SPY", data_dir=tmp_data_dir, interval="1h")
        _, kwargs = mock_yf_download.call_args
        assert kwargs.get("interval") == "1h"

    def test_hourly_forces_period_730d(self, mock_yf_download, tmp_data_dir):
        """interval='1h' + period='5y' → period='730d'로 강제"""
        from download import download_symbol
        download_symbol("SPY", data_dir=tmp_data_dir, interval="1h", period="5y")
        _, kwargs = mock_yf_download.call_args
        assert kwargs.get("period") == "730d"

    def test_hourly_cache_works(self, mock_yf_download, tmp_data_dir):
        """시간봉 파일도 캐시 동작"""
        from download import download_symbol
        download_symbol("SPY", data_dir=tmp_data_dir, interval="1h")
        download_symbol("SPY", data_dir=tmp_data_dir, interval="1h")
        assert mock_yf_download.call_count == 1

    def test_cli_interval_option(self):
        """CLI --interval 옵션 파싱"""
        from download import parse_args
        args = parse_args(["--interval", "1h"])
        assert args.interval == "1h"

    def test_cli_interval_default(self):
        """CLI interval 기본값 1d"""
        from download import parse_args
        args = parse_args([])
        assert args.interval == "1d"
