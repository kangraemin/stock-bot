# Phase 1 Step 2: download.py interval 구현

## 변경 사항
- download_symbol()에 interval 파라미터 추가
- 파일명: interval != "1d"이면 {symbol}_{interval}.parquet
- interval="1h"이면 period를 "730d"로 강제
- yfinance.download에 interval 전달
- parse_args에 --interval 옵션 추가
- __main__ 블록에 interval 전달

## 대상 파일
- download.py
