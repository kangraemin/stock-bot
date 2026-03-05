# Phase 1 - Step 3: Phase 1 테스트

## 목표
- Phase 1에서 변경한 모든 모듈의 단위 테스트 작성

## 변경 파일
- `tests/test_strategies.py`
- `tests/test_portfolio.py`
- `tests/test_engine.py`

## 테스트 항목
- generate_signals_with_reasons() 반환값 검증 (signal + reason 컬럼)
- 필터 on/off 조합별 시그널 변화 확인
- RSI 임계값 파라미터화 동작 확인
- portfolio reason 전달 확인
- engine with_reasons=True/False 동작 확인
- 기존 테스트 통과 (하위호환)

## TC

| TC | 검증 내용 | 참조 | 상태 |
|----|----------|------|------|
| TC-1 | generate_signals_with_reasons 기본 구현 | Step 1 TC-1 | ✅ pass |
| TC-2 | RSI 임계값 파라미터화 | Step 1 TC-2 | ✅ pass |
| TC-3 | EMA/MACD/Volume/ADX 필터 | Step 1 TC-3~6 | ✅ pass |
| TC-4 | params 새 필드 포함 | Step 1 TC-7 | ✅ pass |
| TC-5 | BbRsiEma reason 반환 | Step 1 TC-8 | ✅ pass |
| TC-6 | Portfolio buy/sell reason | Step 2 TC-1~3 | ✅ pass |
| TC-7 | Engine with_reasons 플래그 | Step 2 TC-4~5 | ✅ pass |
| TC-8 | 기존 테스트 하위호환 (141/141) | 전체 스위트 | ✅ pass |
