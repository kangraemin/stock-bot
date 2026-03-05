# Phase 1 - Step 1: 전략 시그널 확장

## 목표
- base.py에 `generate_signals_with_reasons()` 추상 메서드 추가
- bb_rsi_ema.py: RSI 임계값(rsi_buy, rsi_sell) 파라미터화
- bb_rsi_ema.py: EMA/MACD/Volume/ADX 필터 on/off 파라미터 추가
- bb_rsi_ema.py: `generate_signals_with_reasons()` 구현 (reason 문자열 반환)

## 변경 파일
- `src/strategies/base.py`
- `src/strategies/bb_rsi_ema.py`

## 완료 조건
- generate_signals_with_reasons()가 DataFrame에 `signal`, `reason` 컬럼 반환
- 기존 generate_signals()는 하위호환 유지
- 필터 파라미터 기본값은 기존 동작과 동일

## TC

| TC | 테스트명 | 검증 내용 | 상태 |
|----|---------|----------|------|
| TC-1 | test_generate_signals_with_reasons_default | Strategy 기본 구현: signals + 빈 reason 반환 | pending |
| TC-2 | test_bb_rsi_ema_custom_rsi_thresholds | rsi_buy/sell threshold 파라미터 작동 | pending |
| TC-3 | test_bb_rsi_ema_ema_filter | ema_filter=True 시 BUY 제한 | pending |
| TC-4 | test_bb_rsi_ema_macd_filter | macd_filter=True 시 BUY 제한 | pending |
| TC-5 | test_bb_rsi_ema_volume_filter | volume_filter=True 시 BUY 제한 | pending |
| TC-6 | test_bb_rsi_ema_adx_filter | adx_filter=True 시 BUY 제한 | pending |
| TC-7 | test_bb_rsi_ema_params_includes_new_fields | params에 새 필드 포함 + 기본값 확인 | pending |
| TC-8 | test_bb_rsi_ema_with_reasons_returns_reasons | BUY/SELL 시그널에 비어있지 않은 reason 반환 | pending |
