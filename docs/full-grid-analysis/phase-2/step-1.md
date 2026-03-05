# Phase 2 - Step 1: data_loader 주간 리샘플링

## 목표
- data_loader.py에 resample_to_weekly() 함수 추가

## 변경 파일
- `backtest/data_loader.py`
- `tests/test_data_loader.py`

## 완료 조건
- 일봉 데이터를 주봉으로 리샘플링 (OHLCV 올바른 집계)
- 빈 데이터 처리

## TC

| TC | 검증 내용 | 테스트 함수 | 상태 |
|----|----------|------------|------|
| TC-1 | OHLCV 집계 규칙 (open=first, high=max, low=min, close=last, volume=sum) | test_resample_weekly_ohlcv_aggregation | pending |
| TC-2 | 반환값 DatetimeIndex 보존 | test_resample_weekly_datetime_index | pending |
| TC-3 | 컬럼명 보존 (open, high, low, close, volume) | test_resample_weekly_columns_preserved | pending |
| TC-4 | 주봉 행 수 < 일봉 행 수 | test_resample_weekly_row_count | pending |
| TC-5 | 빈 DataFrame 입력 시 빈 DataFrame 반환 | test_resample_weekly_empty | pending |
| TC-6 | partial week 처리 (첫 주/마지막 주) | test_resample_weekly_partial_week | pending |
