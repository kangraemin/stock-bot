# Phase 2 Step 1: data_loader.py interval 테스트 + 구현

## 테스트 케이스

| TC | 설명 | 결과 |
|----|------|------|
| TC-1 | load_single에 interval 파라미터 존재 | |
| TC-2 | interval='1h' 시 SPY_1h.parquet 로드 | |
| TC-3 | interval='1d' 기본값 시 SPY.parquet 로드 | |
| TC-4 | load_multi에 interval 파라미터 존재 | |
| TC-5 | load_multi(symbols, interval='1h') 동작 | |

## 대상 파일
- tests/test_data_loader.py
- backtest/data_loader.py
