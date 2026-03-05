# Phase 1 Step 2: download.py

## 목표
yfinance 기반 주식 데이터 다운로드 CLI

## 구현 대상
- `download.py`: 13종목 + SOXX, XLK 다운로드, Parquet 저장, 캐시

## TC

| TC | 설명 | 검증 |
|----|------|------|
| TC-01 | download_symbol() 함수 존재 | callable(download_symbol) |
| TC-02 | Parquet 파일 생성 | data/{SYMBOL}.parquet 존재 |
| TC-03 | 컬럼 정규화 (소문자) | open, high, low, close, volume 컬럼 존재 |
| TC-04 | DatetimeIndex | df.index가 DatetimeIndex |
| TC-05 | 캐시: 24시간 이내 파일은 스킵 | 최근 파일 있으면 다운로드 안 함 |
| TC-06 | --force 옵션으로 캐시 무시 | force=True 시 재다운로드 |
| TC-07 | CLI --symbols 인자 파싱 | argparse로 심볼 목록 받기 |
| TC-08 | CLI --period 인자 파싱 | 기본값 존재, 커스텀 지정 가능 |
| TC-09 | CLI --force 인자 파싱 | store_true 동작 |
| TC-10 | 기본 심볼 = SYMBOLS_BASE + SYMBOLS_3X + 기초자산 | 최소 13종목 이상 |
| TC-11 | data/ 디렉토리 자동 생성 | 디렉토리 없어도 에러 없이 생성 |
| TC-12 | 잘못된 심볼 시 에러 처리 | 예외 발생 안 하고 스킵/경고 |
