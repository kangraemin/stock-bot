# Phase 3 Step 2: 단일 종목 백테스트 엔진

## 목표
단일 종목 run_backtest() 구현

## 구현 대상
- `backtest/engine.py`: run_backtest() - 단일 종목, 결과에 total_trades 포함

## TC

| TC | 설명 | 검증 |
|----|------|------|
| TC-1 | run_backtest 반환 타입 | dict with keys: equity_curve, total_trades, final_equity, trades |
| TC-2 | total_trades 포함 | 결과에 total_trades 키 존재, int 타입 |
| TC-3 | equity_curve 타입 | list of dict (date, equity) |
| TC-4 | 수수료 적용 | fee_rate > 0 시 final_equity < 수수료 없는 경우 |
| TC-5 | HOLD만 시그널 | 모든 시그널 HOLD → 거래 0, equity = capital |
| TC-6 | BUY→SELL 1회 거래 | total_trades == 2 (매수1 + 매도1) |
| TC-7 | 전략 파라미터 전달 | strategy.params가 결과에 포함 |
| TC-8 | 빈 데이터 처리 | 빈 DataFrame → 에러 없이 기본 결과 반환 |

## 결과 ✅
- 8/8 TC 통과 (pytest)
