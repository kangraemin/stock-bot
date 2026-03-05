"""Phase 2 Step 1: data_loader.py TC"""

import logging

import numpy as np
import pandas as pd
import pytest

from backtest.data_loader import load_multi, load_single


@pytest.fixture()
def sample_parquet(tmp_path):
    """테스트용 Parquet 파일 생성 fixture"""
    dates = pd.date_range("2023-01-02", periods=100, freq="B")
    rng = np.random.default_rng(42)
    df = pd.DataFrame(
        {
            "open": rng.uniform(100, 200, 100),
            "high": rng.uniform(100, 200, 100),
            "low": rng.uniform(100, 200, 100),
            "close": rng.uniform(100, 200, 100),
            "volume": rng.integers(1_000_000, 10_000_000, 100),
        },
        index=dates,
    )
    df.index.name = "Date"
    df.to_parquet(tmp_path / "SPY.parquet")
    df.to_parquet(tmp_path / "QQQ.parquet")
    return tmp_path


# ── TC-1: load_single 정상 로드 ──
def test_load_single_ok(sample_parquet):
    df = load_single("SPY", data_dir=sample_parquet)
    assert isinstance(df, pd.DataFrame)
    for col in ("open", "high", "low", "close", "volume"):
        assert col in df.columns


# ── TC-2: load_single 파일 없음 ──
def test_load_single_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_single("NONEXIST", data_dir=tmp_path)


# ── TC-3: load_single 날짜 필터 (start+end) ──
def test_load_single_date_filter(sample_parquet):
    df = load_single(
        "SPY",
        data_dir=sample_parquet,
        start_date="2023-02-01",
        end_date="2023-03-01",
    )
    assert df.index.min() >= pd.Timestamp("2023-02-01")
    assert df.index.max() <= pd.Timestamp("2023-03-01")
    assert len(df) > 0


# ── TC-4: load_single start만 지정 ──
def test_load_single_start_only(sample_parquet):
    df = load_single("SPY", data_dir=sample_parquet, start_date="2023-04-01")
    assert df.index.min() >= pd.Timestamp("2023-04-01")


# ── TC-5: load_single end만 지정 ──
def test_load_single_end_only(sample_parquet):
    df = load_single("SPY", data_dir=sample_parquet, end_date="2023-02-28")
    assert df.index.max() <= pd.Timestamp("2023-02-28")


# ── TC-6: load_single 인덱스 타입 ──
def test_load_single_index_type(sample_parquet):
    df = load_single("SPY", data_dir=sample_parquet)
    assert isinstance(df.index, pd.DatetimeIndex)


# ── TC-7: load_multi 정상 ──
def test_load_multi_ok(sample_parquet):
    result = load_multi(["SPY", "QQQ"], data_dir=sample_parquet)
    assert isinstance(result, dict)
    assert "SPY" in result
    assert "QQQ" in result
    assert isinstance(result["SPY"], pd.DataFrame)


# ── TC-8: load_multi 빈 리스트 ──
def test_load_multi_empty(tmp_path):
    result = load_multi([], data_dir=tmp_path)
    assert result == {}


# ── TC-9: load_multi 일부 심볼 없음 ──
def test_load_multi_partial_missing(sample_parquet, caplog):
    with caplog.at_level(logging.WARNING):
        result = load_multi(["SPY", "NONEXIST"], data_dir=sample_parquet)
    assert "SPY" in result
    assert "NONEXIST" not in result
    assert any("NONEXIST" in msg for msg in caplog.messages)


# ── TC-10: load_multi 날짜 필터 전파 ──
def test_load_multi_date_filter(sample_parquet):
    result = load_multi(
        ["SPY", "QQQ"],
        data_dir=sample_parquet,
        start_date="2023-02-01",
        end_date="2023-03-01",
    )
    for sym in ("SPY", "QQQ"):
        df = result[sym]
        assert df.index.min() >= pd.Timestamp("2023-02-01")
        assert df.index.max() <= pd.Timestamp("2023-03-01")
