# Phase 5 Step 2: runner.py CLI

## 목표
CLI 진입점

## 구현 대상
- `backtest/runner.py`: --symbols, --portfolio, --weights, --rebalance, --fee-rate, --grid-search, --capital, --report, --compare-buyhold, --compare-presets, --single-vs-mixed

## TC

| TC | 설명 | 검증 |
|----|------|------|
| TC-1 | parse_args 기본값 | symbols 기본, capital=2000 |
| TC-2 | --symbols 파싱 | 커스텀 심볼 리스트 |
| TC-3 | --portfolio 플래그 | True/False |
| TC-4 | --grid-search 플래그 | True/False |
| TC-5 | --compare-presets 플래그 | True/False |
| TC-6 | --single-vs-mixed 플래그 | True/False |
| TC-7 | --capital 파싱 | float 변환 |
| TC-8 | --fee-rate 파싱 | float 변환 |

## 결과 ✅
- 8/8 TC 통과 (pytest)
