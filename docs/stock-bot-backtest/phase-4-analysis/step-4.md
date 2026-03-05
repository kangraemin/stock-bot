# Phase 4 Step 4: comparisons.py

## 목표
포트폴리오 프리셋 비교 모듈

## 구현 대상
- `backtest/comparisons.py`: run_single_vs_portfolio(), run_preset_comparison()
- 비교 지표: 수익률, MDD, Sharpe, 거래 횟수, B&H 대비 초과수익

## TC

| TC | 설명 | 검증 |
|----|------|------|
| TC-1 | run_single_vs_portfolio 반환 | dict with single_results, portfolio_result |
| TC-2 | run_preset_comparison 반환 | dict with preset_name -> metrics |
| TC-3 | 비교 지표 포함 | total_return, mdd, sharpe, total_trades |
| TC-4 | PRESETS 접근 | config.py PRESET_* 사용 |
| TC-5 | 빈 프리셋 처리 | 빈 dict → 에러 없이 빈 결과 |
| TC-6 | excess_return 포함 | B&H 대비 초과수익 포함 |

## 결과 ✅
- 6/6 TC 통과 (pytest)
