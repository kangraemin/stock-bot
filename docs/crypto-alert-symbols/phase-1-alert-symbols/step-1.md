# Step 1: alert.py SYMBOLS dict에 7종목 추가

## 테스트 케이스

| # | TC | 예상 결과 | 실제 |
|---|-----|----------|------|
| 1 | `from alert import SYMBOLS; len(SYMBOLS) == 16` | 기존 9 + 신규 7 = 16 | ✅ |
| 2 | 7종목 모두 buy_only=True | True | ✅ |
| 3 | 7종목 모두 sell_rsi=None, rebuy_rsi=None | None | ✅ |
| 4 | MSTR/HOOD/MARA/COIN/WGMI/CLSK buy_rsi=30 | 30 | ✅ |
| 5 | BITQ buy_rsi=25 | 25 | ✅ |

## 구현

alert.py SYMBOLS dict에 NVDA 아래 7종목 추가 (buy_only 패턴).
