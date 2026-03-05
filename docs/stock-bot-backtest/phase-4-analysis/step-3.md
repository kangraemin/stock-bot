# Phase 4 Step 3: grid_search.py

## 목표
파라미터 그리드 서치 최적화

## 구현 대상
- `backtest/grid_search.py`: ~9700 조합, total_trades + vs_buyhold_excess 필수

## TC

| TC | 설명 | 검증 |
|----|------|------|
| TC-1 | grid_search 반환 | list of dict (params + metrics) |
| TC-2 | 결과에 total_trades | 각 결과에 total_trades 포함 |
| TC-3 | 결과에 vs_buyhold_excess | B&H 대비 초과수익 포함 |
| TC-4 | 결과 정렬 | sharpe 기준 내림차순 |
| TC-5 | 파라미터 조합 생성 | 그리드 조합 수 검증 |
| TC-6 | top_n 필터 | 상위 N개만 반환 |

## 결과 ✅
- 6/6 TC 통과 (pytest)
