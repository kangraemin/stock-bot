# GGLL/NVDA 매수 타이밍 전용 알림 추가

## Context
GGLL(구글 2x)과 NVDA(엔비디아)는 OOS 검증에서 풀 RSI 전략이 B&H를 이기지 못했다.
RSI 과매도 진입 시 "매수 적기" 알림만 제공하고, 매도 시그널은 생성하지 않는다.

## Phase 1: alert.py buy_only 모드 추가
- SYMBOLS에 GGLL/NVDA 추가 (buy_only=True)
- check_symbol() buy_only 분기 (BUY_TIMING 시그널, 스팸 방지)
- main() 메시지 포맷 수정 (BUY_TIMING 표시)
- _what_to_do() buy_only 전용 메시지

## Phase 2: 테스트 추가
- buy_only check_symbol/what_to_do/config 테스트
