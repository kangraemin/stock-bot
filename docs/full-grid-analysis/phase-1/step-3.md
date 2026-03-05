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
