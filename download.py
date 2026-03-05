"""yfinance 기반 주식 데이터 다운로드 CLI"""

import argparse
import pathlib
import time

import pandas as pd
import yfinance

from config import SYMBOLS_BASE, SYMBOLS_3X, LEVERAGE_MAP

DATA_DIR = pathlib.Path("data")

# 기초자산 중 SYMBOLS_BASE에 없는 것 추가 (SOXX, XLK 등)
_UNDERLYING = set(LEVERAGE_MAP.values())
_EXTRA = sorted(_UNDERLYING - set(SYMBOLS_BASE) - set(SYMBOLS_3X))
DEFAULT_SYMBOLS = list(SYMBOLS_BASE) + list(SYMBOLS_3X) + _EXTRA + ["SOXX", "XLK"]
# 중복 제거 & 순서 유지
DEFAULT_SYMBOLS = list(dict.fromkeys(DEFAULT_SYMBOLS))

_CACHE_SECONDS = 24 * 3600


def download_symbol(
    symbol: str,
    data_dir: pathlib.Path = DATA_DIR,
    force: bool = False,
    period: str = "5y",
) -> None:
    data_dir = pathlib.Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)

    path = data_dir / f"{symbol}.parquet"

    # 캐시 체크
    if not force and path.exists():
        age = time.time() - path.stat().st_mtime
        if age < _CACHE_SECONDS:
            return

    df = yfinance.download(symbol, period=period, progress=False, auto_adjust=True)

    if df is None or df.empty:
        return

    # MultiIndex 컬럼 처리 (yfinance 최신 버전)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    # 컬럼 소문자 정규화
    df.columns = [c.lower() for c in df.columns]

    df.to_parquet(path)


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="주식 데이터 다운로드")
    parser.add_argument(
        "--symbols", nargs="+", default=DEFAULT_SYMBOLS, help="다운로드할 심볼 목록"
    )
    parser.add_argument("--period", default="5y", help="다운로드 기간 (기본: 5y)")
    parser.add_argument("--force", action="store_true", help="캐시 무시하고 재다운로드")
    return parser.parse_args(argv)


if __name__ == "__main__":
    args = parse_args()
    for sym in args.symbols:
        print(f"Downloading {sym}...")
        download_symbol(sym, force=args.force, period=args.period)
