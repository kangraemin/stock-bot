"""Parquet 파일 로드 및 날짜 필터링"""

import logging
import pathlib
from typing import Optional

import pandas as pd

from download import DATA_DIR

logger = logging.getLogger(__name__)


def load_single(
    symbol: str,
    data_dir: pathlib.Path = DATA_DIR,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    interval: str = "1d",
) -> pd.DataFrame:
    suffix = f"_{interval}" if interval != "1d" else ""
    path = pathlib.Path(data_dir) / f"{symbol}{suffix}.parquet"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found")

    df = pd.read_parquet(path)
    df.index = pd.to_datetime(df.index)

    if start_date:
        df = df[df.index >= pd.Timestamp(start_date)]
    if end_date:
        df = df[df.index <= pd.Timestamp(end_date)]

    return df


def resample_to_weekly(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    return df.resample("W").agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }).dropna()


def load_multi(
    symbols: list[str],
    data_dir: pathlib.Path = DATA_DIR,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    interval: str = "1d",
) -> dict[str, pd.DataFrame]:
    result = {}
    for sym in symbols:
        try:
            result[sym] = load_single(
                sym, data_dir=data_dir, start_date=start_date, end_date=end_date,
                interval=interval,
            )
        except FileNotFoundError:
            logger.warning("%s: parquet file not found, skipping", sym)
    return result
