# Phase 2 - Step 2: Grid Search 확장 + 병렬화

## 목표
- grid_search.py: DEFAULT_GRID에 새 파라미터(rsi_buy, rsi_sell, ema_filter, macd_filter, volume_filter, adx_filter) 추가
- grid_search.py: run_full_grid_search() 구현
  - 13종목 × 49,152 조합 × 2수수료 × 2시간대 × 3기간
  - ProcessPoolExecutor 병렬화
  - 2-tier 최적화: 1차 coarse grid → 2차 fine grid (상위 파라미터 주변)
- 종목별 Top 5 결과 반환

## 변경 파일
- `src/grid_search.py`

## 완료 조건
- run_full_grid_search()가 종목별 Top 5 결과 dict 반환
- 병렬 실행으로 성능 확보
- 진행률 표시 (tqdm 또는 로깅)
