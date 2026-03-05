# Phase 2 - Step 2: Grid Search 확장 + 병렬화

## 목표
- grid_search.py: DEFAULT_GRID에 새 파라미터(rsi_buy_threshold, rsi_sell_threshold, ema_filter, macd_filter, volume_filter, adx_filter) 추가 → 10개 파라미터, 49,152 조합
- grid_search.py: run_full_grid_search() 구현
  - 다중 심볼 × 조합 × fee_rates × timeframes × periods
  - ProcessPoolExecutor 병렬화
  - 2-tier 최적화: 1차 coarse grid → 2차 fine grid (상위 파라미터 주변)
- 종목별 Top N 결과 반환

## 변경 파일
- `backtest/grid_search.py`

## 완료 조건
- ✅ DEFAULT_GRID 10개 파라미터 (49,152 조합)
- ✅ run_full_grid_search() 반환 구조 정상
- ✅ 기존 6개 + 신규 8개 = 14/14 tests passed

## TC

| TC | 검증 내용 | 테스트 함수 | 상태 |
|----|----------|------------|------|
| TC-7 | DEFAULT_GRID 10개 파라미터 키 | test_default_grid_has_10_params | ❌ |
| TC-8 | DEFAULT_GRID 조합 수 49,152 | test_default_grid_combo_count_49152 | ❌ |
| TC-9 | generate_param_combos에 새 파라미터 포함 | test_param_combos_include_new_params | ❌ |
| TC-10 | run_full_grid_search 존재 및 기본 반환 구조 | test_full_grid_search_return_structure | ❌ |
| TC-11 | run_full_grid_search 다중 심볼 → 심볼별 키 | test_full_grid_search_multi_symbol | ❌ |
| TC-12 | run_full_grid_search top_n 제한 | test_full_grid_search_top_n | ❌ |
| TC-13 | run_full_grid_search fee_rates 파라미터 | test_full_grid_search_fee_rates | ❌ |
| TC-14 | run_full_grid_search timeframes (daily/weekly) | test_full_grid_search_timeframes | ❌ |
