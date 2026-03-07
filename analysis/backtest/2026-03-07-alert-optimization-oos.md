# Alert.py 최적화 + OOS 검증

- **날짜**: 2026-03-07
- **카테고리**: backtest
- **심볼**: SOXL, TQQQ, SPXL, TNA, QLD, UWM, QQQ
- **조합 수**: 16,800 (in-sample) + 106 rolling OOS windows

## 요약

alert.py 파라미터 최적화 그리드 서치(16,800 조합) + OOS 검증 결과, **현행 유지가 최적**. sell+sma200 필터가 in-sample에서 유망했으나 rolling OOS에서 24% 승률로 기각.

## 그리드 서치 설계

- **rebuy_rsi**: 10개 값 (25~70, 5 간격)
- **sell 필터**: 4종 (현행, +sma200, +bb_upper, +sma200+bb)
- **buy 필터**: 4종 (현행, +bb_lower, +ema, +bb+ema)
- **EMA 윈도우**: 3종 (10, 20, 50)
- **종목**: 7개 (alert.py 매도 있는 종목)
- **기간**: 5종 (1y, 3y, 5y, 7y, full)
- **총**: 10 × 4 × 4 × 3 × 7 × 5 = 16,800

## In-Sample 결과

| sell 필터 | 평균 Sharpe | 평균 수익률 | B&H 초과 비율 |
|-----------|-----------|-----------|-------------|
| 현행 (RSI only) | 0.42 | +87% | 34% |
| +sma200 | 0.48 | +95% | 38% |
| +bb_upper | 0.40 | +82% | 32% |
| +sma200+bb | 0.45 | +89% | 36% |

sell+sma200가 가장 유망해 보임.

## OOS 검증

### Single Split (train<2020, test≥2020)
- sell+sma200: 5/7 종목 개선 → 유망해 보임

### Rolling OOS (3yr train → 2yr test, 1yr sliding)
- **106 windows × 7 symbols**
- sell+sma200 승률: **25/106 (24%)** → **FAIL**
- 현행이 76% 승률로 압도

### 시장 국면 분석
- 약세장 (2022): sma200 필터 유효 (하락장에서 매도 방지)
- 강세장 (2023~): sma200 필터가 매도 지연 → 수익 손실
- 강세장이 더 길므로 전체적으로 손해

## 결론

1. **현행 alert.py 유지** — 추가 필터 불필요
2. sell+sma200는 약세장 전용. 강세장에서 역효과
3. rebuy_rsi, buy 필터 변형도 유의미한 개선 없음
4. **"단순한 전략이 robust"** 재확인

## 다음 액션

- 현행 유지. 파라미터 변경 불필요
- RSI 매수 타이밍만 활용 vs B&H 비교 백테스트 예정 (36종목 × 4기간)
