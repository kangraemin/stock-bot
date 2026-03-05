# Phase 2 Step 3: BB+RSI+EMA 전략

## 목표
Bollinger Band + RSI + EMA 평균회귀 전략 구현

## 구현 대상
- `backtest/strategies/bb_rsi_ema.py`: 롱 시그널 생성, 파라미터 생성자 주입

## TC

| TC | 설명 | 검증 |
|----|------|------|
| TC-1 | Strategy 상속 확인 | isinstance(BbRsiEma(), Strategy) |
| TC-2 | 기본 파라미터 | bb_window=20, bb_std=2, rsi_window=14, ema_window=50 |
| TC-3 | 커스텀 파라미터 주입 | 생성자에서 파라미터 오버라이드 |
| TC-4 | generate_signals 반환 타입 | pd.Series, len == len(df) |
| TC-5 | 시그널 값 범위 | Signal.BUY, SELL, HOLD만 포함 |
| TC-6 | 데이터 부족 시 안전 | 짧은 데이터 → 에러 없이 HOLD |
| TC-7 | STRATEGIES 레지스트리 등록 | STRATEGIES["bb_rsi_ema"] == BbRsiEma |
| TC-8 | BUY 시그널 생성 조건 | close < BB하한 + RSI < 30 + close > EMA → BUY |

## 결과 ✅
- 16/16 TC 통과 (Step 2: 8 + Step 3: 8, pytest)
