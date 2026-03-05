# Phase 3 Step 1: Portfolio 클래스

## 목표
멀티 포지션 포트폴리오 관리

## 구현 대상
- `backtest/portfolio.py`: buy/sell 수수료 차감, get_total_equity, get_weights, trade_log, trade_count

## TC

| TC | 설명 | 검증 |
|----|------|------|
| TC-1 | Portfolio 초기화 | cash=capital, positions 빈 dict |
| TC-2 | buy 수수료 차감 | buy 후 cash 감소 = price*qty*(1+fee) |
| TC-3 | sell 수수료 차감 | sell 후 cash 증가 = price*qty*(1-fee) |
| TC-4 | buy 잔고 부족 | 자금 부족 시 매수 불가 (False 반환) |
| TC-5 | sell 미보유 종목 | 보유하지 않은 종목 매도 불가 |
| TC-6 | get_total_equity | cash + sum(positions*prices) |
| TC-7 | get_weights | 각 종목 비중 합 <= 1.0 |
| TC-8 | trade_log 기록 | buy/sell 후 trade_log에 기록 추가 |
| TC-9 | trade_count | 거래 횟수 정확히 카운트 |
| TC-10 | update_equity | 일별 equity 기록 |

## 결과 ✅
- 10/10 TC 통과 (pytest)
