# Phase 4 Step 2: buyhold.py

## 목표
Buy & Hold 비교 모듈

## 구현 대상
- `backtest/buyhold.py`: compute_buyhold(), compare_vs_buyhold(), compare_by_period()

## TC

| TC | 설명 | 검증 |
|----|------|------|
| TC-1 | compute_buyhold 반환 | dict with final_equity, total_return |
| TC-2 | compute_buyhold 수수료 | 매수 시 수수료 적용 |
| TC-3 | compare_vs_buyhold | strategy vs buyhold 비교 dict |
| TC-4 | excess_return 계산 | strategy_return - buyhold_return |
| TC-5 | compare_by_period | 기간별 비교 리스트 |
| TC-6 | 빈 데이터 처리 | 에러 없이 기본값 |

## 결과 ✅
- 6/6 TC 통과 (pytest)
