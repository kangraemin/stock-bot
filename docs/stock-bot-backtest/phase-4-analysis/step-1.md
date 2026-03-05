# Phase 4 Step 1: metrics.py

## 목표
성과 지표 계산 모듈

## 구현 대상
- `backtest/metrics.py`: 수익률, MDD, Sharpe, Calmar, Information Ratio, Turnover, avg_holding_days, total_trades

## TC

| TC | 설명 | 검증 |
|----|------|------|
| TC-1 | total_return 계산 | (최종-초기)/초기 |
| TC-2 | max_drawdown 계산 | 음수 값, 올바른 범위 |
| TC-3 | sharpe_ratio 계산 | float 반환 |
| TC-4 | calmar_ratio 계산 | total_return / abs(mdd) |
| TC-5 | total_trades 포함 | 거래 횟수 정수 |
| TC-6 | compute_metrics 반환 | dict with 모든 지표 키 |
| TC-7 | 빈 equity curve | 에러 없이 기본값 반환 |
| TC-8 | annualized_return | 연간 수익률 계산 |
