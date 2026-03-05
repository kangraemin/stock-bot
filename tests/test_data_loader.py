"""Phase 2 Step 1: data_loader.py TC"""

import logging

import numpy as np
import pandas as pd
import pytest

from backtest.data_loader import load_multi, load_single

try:
    from backtest.data_loader import resample_to_weekly
except ImportError:

    def resample_to_weekly(*args, **kwargs):
        raise NotImplementedError("resample_to_weekly not implemented yet")


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


# ── Phase 2 Step 1: resample_to_weekly TC ──


@pytest.fixture()
def daily_df():
    """3주 분량 일봉 데이터 (15 영업일)"""
    dates = pd.date_range("2023-01-02", periods=15, freq="B")
    return pd.DataFrame(
        {
            "open": [100 + i for i in range(15)],
            "high": [110 + i for i in range(15)],
            "low": [90 + i for i in range(15)],
            "close": [105 + i for i in range(15)],
            "volume": [1000 * (i + 1) for i in range(15)],
        },
        index=dates,
    )


# TC-1: OHLCV 집계 규칙
def test_resample_weekly_ohlcv_aggregation(daily_df):
    weekly = resample_to_weekly(daily_df)
    # 첫 번째 주 (2023-01-02 ~ 2023-01-06, 5일)
    first_week = weekly.iloc[0]
    first_5 = daily_df.iloc[:5]
    assert first_week["open"] == first_5["open"].iloc[0]
    assert first_week["high"] == first_5["high"].max()
    assert first_week["low"] == first_5["low"].min()
    assert first_week["close"] == first_5["close"].iloc[-1]
    assert first_week["volume"] == first_5["volume"].sum()


# TC-2: DatetimeIndex 보존
def test_resample_weekly_datetime_index(daily_df):
    weekly = resample_to_weekly(daily_df)
    assert isinstance(weekly.index, pd.DatetimeIndex)


# TC-3: 컬럼명 보존
def test_resample_weekly_columns_preserved(daily_df):
    weekly = resample_to_weekly(daily_df)
    for col in ("open", "high", "low", "close", "volume"):
        assert col in weekly.columns


# TC-4: 주봉 행 수 < 일봉 행 수
def test_resample_weekly_row_count(daily_df):
    weekly = resample_to_weekly(daily_df)
    assert len(weekly) < len(daily_df)
    assert len(weekly) == 3  # 3주


# TC-5: 빈 DataFrame 입력
def test_resample_weekly_empty():
    empty = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    empty.index = pd.DatetimeIndex([], name="Date")
    result = resample_to_weekly(empty)
    assert isinstance(result, pd.DataFrame)
    assert len(result) == 0


# TC-6: partial week 처리
def test_resample_weekly_partial_week():
    # 수요일부터 시작 → 첫 주는 3일(수,목,금)
    dates = pd.date_range("2023-01-04", periods=8, freq="B")  # Wed~next Fri
    df = pd.DataFrame(
        {
            "open": range(8),
            "high": range(10, 18),
            "low": range(8),
            "close": range(1, 9),
            "volume": [100] * 8,
        },
        index=dates,
    )
    weekly = resample_to_weekly(df)
    assert len(weekly) >= 2
    # 첫 partial week의 open은 첫 날 open
    assert weekly.iloc[0]["open"] == df.iloc[0]["open"]
