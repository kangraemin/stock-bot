# Phase 4 Step 1: grid_search.py hourly 테스트 + 구현

## 테스트 케이스

| TC | 설명 | 결과 |
|----|------|------|
| TC-1 | run_grid_search에 periods_per_year 파라미터 존재 | |
| TC-2 | run_full_grid_search에 hourly_data 파라미터 존재 | |
| TC-3 | timeframes=["hourly"] + hourly_data 전달 시 hourly 결과 포함 | |
| TC-4 | hourly_data 없이 timeframes에 hourly → 해당 tf 스킵 | |
| TC-5 | timeframes=["daily","hourly"] 혼합 동작 | |

## 대상 파일
- tests/test_grid_search.py
- backtest/grid_search.py
