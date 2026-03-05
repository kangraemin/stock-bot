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
