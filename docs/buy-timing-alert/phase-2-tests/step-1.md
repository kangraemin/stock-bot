# Step 1: buy_only 테스트 추가

## TC (테스트 정의)

| # | 항목 | 예상 결과 | 실제 |
|---|------|----------|------|
| 1 | test_buy_only_buy_timing_signal: RSI < buy_rsi, 첫 진입 → BUY_TIMING | PASS | |
| 2 | test_buy_only_no_signal_above: RSI >= buy_rsi → signal=None | PASS | |
| 3 | test_buy_only_spam_prevention: 연속 과매도 → 두 번째 시그널 없음 | PASS | |
| 4 | test_buy_only_what_to_do: buy_only _what_to_do 분기 검증 | PASS | |
| 5 | pytest 전체 통과 | PASS | |

[STEP:1:테스트정의완료]
