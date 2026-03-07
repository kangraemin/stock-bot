# Step 2: 테스트 추가

## 테스트 케이스

| # | TC | 예상 결과 | 실제 |
|---|-----|----------|------|
| 1 | pytest tests/test_alert_buy_only.py -v 통과 | PASS | ✅ 16/16 |
| 2 | pytest tests/ 전체 통과 | PASS | ✅ 224/225 (기존 known issue 1개) |

## 구현

tests/test_alert_buy_only.py에 코인 종목 설정 검증 테스트 추가.
