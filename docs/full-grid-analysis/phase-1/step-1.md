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
