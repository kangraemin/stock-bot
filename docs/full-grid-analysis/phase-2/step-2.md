# Phase 2 - Step 2: Grid Search 확장 + 병렬화

## 목표
- grid_search.py: DEFAULT_GRID에 새 파라미터 추가 → 10개 파라미터, 49,152 조합
- grid_search.py: run_full_grid_search() 구현
  - 다중 심볼 × 조합 × fee_rates × timeframes × periods
  - ProcessPoolExecutor 병렬화 (n_jobs)

## 변경 파일
- `backtest/grid_search.py` — DEFAULT_GRID 확장, run_full_grid_search() 추가

## 구현 상세

### DEFAULT_GRID 확장 (10개 파라미터)
- 기존 4개: bb_window, bb_std, rsi_window, ema_window
- 신규 6개: rsi_buy_threshold, rsi_sell_threshold, ema_filter, macd_filter, volume_filter, adx_filter
- 총 49,152 조합

### run_full_grid_search()
- 반환: `{symbol: {timeframe: {period: {fee_label: [results]}}}}`
- fee_rates 기본값: [STANDARD, EVENT] → "standard" / "event" 라벨
- periods 기본값: ["1y", "3y", "5y"] → 끝에서 N년 슬라이싱
- timeframes 기본값: ["daily", "weekly"] → weekly는 resample_to_weekly() 사용
- 각 조합에서 기존 run_grid_search() 호출, top_n 적용
- n_jobs > 1이면 ProcessPoolExecutor로 심볼별 병렬 실행

## 완료 조건
- ✅ DEFAULT_GRID 10개 파라미터 (49,152 조합)
- ✅ run_full_grid_search() 반환 구조 정상
- ✅ 기존 6개 + 신규 8개 = 14/14 tests passed (291s)

## TC

| TC | 검증 내용 | 테스트 함수 | 상태 |
|----|----------|------------|------|
| TC-7 | DEFAULT_GRID 10개 파라미터 키 | test_default_grid_has_10_params | ✅ pass |
| TC-8 | DEFAULT_GRID 조합 수 49,152 | test_default_grid_combo_count_49152 | ✅ pass |
| TC-9 | generate_param_combos에 새 파라미터 포함 | test_param_combos_include_new_params | ✅ pass |
| TC-10 | run_full_grid_search 존재 및 기본 반환 구조 | test_full_grid_search_return_structure | ✅ pass |
| TC-11 | run_full_grid_search 다중 심볼 → 심볼별 키 | test_full_grid_search_multi_symbol | ✅ pass |
| TC-12 | run_full_grid_search top_n 제한 | test_full_grid_search_top_n | ✅ pass |
| TC-13 | run_full_grid_search fee_rates 파라미터 | test_full_grid_search_fee_rates | ✅ pass |
| TC-14 | run_full_grid_search timeframes (daily/weekly) | test_full_grid_search_timeframes | ✅ pass |
