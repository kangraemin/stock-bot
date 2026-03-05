# Phase 1 - Step 1: 전략 시그널 확장

## 목표
- base.py에 `generate_signals_with_reasons()` 기본 메서드 추가
- bb_rsi_ema.py: RSI 임계값(rsi_buy, rsi_sell) 파라미터화
- bb_rsi_ema.py: EMA/MACD/Volume/ADX 필터 on/off 파라미터 추가
- bb_rsi_ema.py: `generate_signals_with_reasons()` 구현 (reason 문자열 반환)

## 변경 파일
- `backtest/strategies/base.py` — `generate_signals_with_reasons()` 기본 구현 추가
- `backtest/strategies/bb_rsi_ema.py` — 6개 신규 파라미터, 필터 로직, reason 생성

## 구현 상세

### base.py
- `generate_signals_with_reasons(self, df)`: non-abstract 기본 구현
  - `generate_signals()` 결과 + 빈 reason Series 반환

### bb_rsi_ema.py
- 신규 `__init__` 파라미터 (모두 기본값으로 하위호환):
  - `rsi_buy_threshold=35`, `rsi_sell_threshold=65`
  - `ema_filter=False`, `macd_filter=False`, `volume_filter=False`, `adx_filter=False`
- `generate_signals()`: 하드코딩 35/65 → 파라미터 사용, 필터 AND 조건 적용
- `generate_signals_with_reasons()`: BUY/SELL 시그널에 reason 문자열 생성
  - BUY: `"Close(X) < BB_lower(Y), RSI(Z) < 35, EMA OK, MACD OK"` 등
  - SELL: `"Close(X) > BB_upper(Y), RSI(Z) > 65"`
- `params` 프로퍼티에 6개 신규 필드 포함

## 완료 조건
- ✅ generate_signals_with_reasons()가 (signals, reasons) 튜플 반환
- ✅ 기존 generate_signals()는 하위호환 유지
- ✅ 필터 파라미터 기본값은 기존 동작과 동일
- ✅ 24/24 tests passed

## TC

| TC | 테스트명 | 검증 내용 | 상태 |
|----|---------|----------|------|
| TC-1 | test_generate_signals_with_reasons_default | Strategy 기본 구현: signals + 빈 reason 반환 | ✅ pass |
| TC-2 | test_bb_rsi_ema_custom_rsi_thresholds | rsi_buy/sell threshold 파라미터 작동 | ✅ pass |
| TC-3 | test_bb_rsi_ema_ema_filter | ema_filter=True 시 BUY 제한 | ✅ pass |
| TC-4 | test_bb_rsi_ema_macd_filter | macd_filter=True 시 BUY 제한 | ✅ pass |
| TC-5 | test_bb_rsi_ema_volume_filter | volume_filter=True 시 BUY 제한 | ✅ pass |
| TC-6 | test_bb_rsi_ema_adx_filter | adx_filter=True 시 BUY 제한 | ✅ pass |
| TC-7 | test_bb_rsi_ema_params_includes_new_fields | params에 새 필드 포함 + 기본값 확인 | ✅ pass |
| TC-8 | test_bb_rsi_ema_with_reasons_returns_reasons | BUY/SELL 시그널에 비어있지 않은 reason 반환 | ✅ pass |
