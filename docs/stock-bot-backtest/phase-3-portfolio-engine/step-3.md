# Phase 3 Step 3: 포트폴리오 백테스트 + 리밸런싱

## 목표
멀티 포지션 포트폴리오 백테스트 + 리밸런싱

## 구현 대상
- `backtest/engine.py`: run_portfolio_backtest() 추가
- `backtest/rebalancer.py`: equal/custom/risk_parity, 임계값 2%p

## TC

| TC | 설명 | 검증 |
|----|------|------|
| TC-1 | run_portfolio_backtest 반환 타입 | dict with equity_curve, total_trades, final_equity |
| TC-2 | 멀티 심볼 처리 | 2개 이상 심볼로 실행 |
| TC-3 | rebalancer equal 모드 | 균등 비중으로 리밸런싱 |
| TC-4 | rebalancer custom 모드 | 지정 비중으로 리밸런싱 |
| TC-5 | 리밸런싱 임계값 2%p | 차이 < 2%p → 리밸런싱 스킵 |
| TC-6 | 리밸런싱 거래 횟수 | 리밸런싱 시 trade_count 증가 |
| TC-7 | monthly 리밸런싱 | 월 1회 리밸런싱 |
| TC-8 | 포트폴리오 결과에 total_trades | 결과에 total_trades 필수 |

## 결과 ✅
- 8/8 TC 통과 (pytest)
