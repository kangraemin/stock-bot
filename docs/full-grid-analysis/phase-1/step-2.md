# Phase 1 - Step 2: reason 전달 경로

## 목표
- portfolio.py: reason 파라미터 수용 및 거래 기록에 포함
- engine.py: with_reasons 옵션으로 reason 포함 백테스트 실행

## 변경 파일
- `src/portfolio.py`
- `src/engine.py`

## 완료 조건
- engine이 with_reasons=True일 때 전략의 generate_signals_with_reasons() 호출
- 거래 기록(trades)에 reason 필드 포함
- with_reasons=False(기본)이면 기존 동작과 동일

## TC

| TC | 테스트명 | 파일 | 검증 내용 | 상태 |
|----|---------|------|----------|------|
| TC-1 | test_buy_with_reason | test_portfolio.py | buy(reason="...") 시 trade_log에 reason 포함 | pending |
| TC-2 | test_sell_with_reason | test_portfolio.py | sell(reason="...") 시 trade_log에 reason 포함 | pending |
| TC-3 | test_buy_sell_default_reason_empty | test_portfolio.py | reason 미전달 시 빈 문자열 기본값 | pending |
| TC-4 | test_run_backtest_with_reasons_flag | test_engine.py | with_reasons=True 시 generate_signals_with_reasons 호출 | pending |
| TC-5 | test_run_backtest_with_reasons_trades_have_reason | test_engine.py | with_reasons=True 시 trades에 reason 키 포함 | pending |
| TC-6 | test_run_backtest_default_no_reasons | test_engine.py | with_reasons=False(기본) 시 기존 동작 유지 | pending |
