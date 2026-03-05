# Phase 2 Step 2: Strategy ABC + Registry

## 목표
전략 추상 클래스 및 레지스트리

## 구현 대상
- `backtest/strategies/base.py`: Strategy ABC (generate_signals, params)
- `backtest/strategies/__init__.py`: STRATEGIES 레지스트리
- `backtest/__init__.py`

## TC

| TC | 설명 | 검증 |
|----|------|------|
| TC-1 | Strategy ABC 인스턴스화 불가 | ABC라서 직접 생성 시 TypeError |
| TC-2 | generate_signals 추상 메서드 | 서브클래스에서 구현 필수 |
| TC-3 | params 프로퍼티 | 전략 파라미터 dict 반환 |
| TC-4 | 서브클래스 정상 구현 | generate_signals + params 구현 시 인스턴스화 OK |
| TC-5 | generate_signals 반환 타입 | pd.Series 반환, index=DatetimeIndex |
| TC-6 | Signal enum 값 | BUY, SELL, HOLD 존재 |
| TC-7 | STRATEGIES 레지스트리 dict | dict[str, type] 형태 |
| TC-8 | 레지스트리에서 전략 조회 | STRATEGIES["bb_rsi_ema"] 접근 가능 |

## 결과 ✅
- 8/8 TC 통과 (pytest)
