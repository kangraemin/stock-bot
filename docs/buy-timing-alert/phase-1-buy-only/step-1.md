# Step 1: SYMBOLS에 GGLL/NVDA 추가 + check_symbol buy_only 분기 + 메시지 포맷

## TC (테스트 정의)

| # | 항목 | 예상 결과 | 실제 |
|---|------|----------|------|
| 1 | SYMBOLS에 GGLL, NVDA 존재, buy_only=True | PASS | ✅ |
| 2 | check_symbol() buy_only RSI < buy_rsi → signal="BUY_TIMING" | PASS | ✅ |
| 3 | check_symbol() buy_only RSI >= buy_rsi → signal=None | PASS | ✅ |
| 4 | check_symbol() buy_only 연속 과매도 → 두 번째는 시그널 없음 (스팸 방지) | PASS | ✅ |
| 5 | _what_to_do() buy_only RSI < buy_rsi → "저점 매수 구간" | PASS | ✅ |
| 6 | _what_to_do() buy_only RSI >= buy_rsi → "B&H 보유 유지" | PASS | ✅ |
| 7 | 구문 검사 통과 | PASS | ✅ |
| 8 | pytest 8/8 통과 + 기존 테스트 209 passed | PASS | ✅ |

[STEP:1:테스트통과]
