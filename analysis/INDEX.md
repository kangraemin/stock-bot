# Analysis Index

| 날짜 | 카테고리 | 제목 | 파일 | 핵심 결과 |
|------|---------|------|------|----------|
| 2026-03-06 | backtest | SOXL 임계값 전략 | [링크](backtest/2026-03-06-soxl-threshold-strategy.md) | 1%/1%/1% = -97.3%. Best: 1.5%/3%/5% = +60.1% |
| 2026-03-06 | backtest | SOXL 매수 타이밍 전략 | [링크](backtest/2026-03-06-soxl-buy-timing.md) | B&H +9,020% 압도. 타이밍 전략 모두 B&H 미달. DCA+MeanRev 하이브리드 추천 |
| 2026-03-06 | backtest | Sell-Timing 파라미터 그리드 서치 | [링크](backtest/2026-03-06-sell-timing-grid-search.md) | 38종목x240조합. 1y 97% 승률, full 34%. Best: RSI>65+SMA200→RSI<25. 레버리지ETF에서 가장 효과적 |
| 2026-03-07 | backtest | 매크로 레짐 감지 | [링크](backtest/2026-03-07-macro-regime-detection.md) | 구리/유가/VIX/금/금리/달러 레짐. 4쌍x240조합. B&H 3x 승률 0~2%. TNA만 +474%. MaxDD 15~25%p 개선 |
| 2026-03-07 | backtest | 매크로 레짐 + RSI 결합 | [링크](backtest/2026-03-07-macro-regime-rsi-combined.md) | 레짐을 필터로 활용. SOXL +385,753%(90B/89S). filter_block+force가 SPXL/TNA에서 압도. confirm=10d 최적 |
| 2026-03-07 | backtest | 매크로 레짐 심층 분석 | [링크](backtest/2026-03-07-macro-regime-deep-analysis.md) | OOS: SOXL 과적합(0%), TNA만 유효(+117%). Ablation: oil+tnx 최강, copper/gold 무효. 실전: 종목별 다른 전략 필요 |
