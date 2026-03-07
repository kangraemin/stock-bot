# Analysis Index

| 날짜 | 카테고리 | 제목 | 파일 | 핵심 결과 |
|------|---------|------|------|----------|
| 2026-03-06 | backtest | SOXL 임계값 전략 | [링크](backtest/2026-03-06-soxl-threshold-strategy.md) | 1%/1%/1% = -97.3%. Best: 1.5%/3%/5% = +60.1% |
| 2026-03-06 | backtest | SOXL 매수 타이밍 전략 | [링크](backtest/2026-03-06-soxl-buy-timing.md) | B&H +9,020% 압도. 타이밍 전략 모두 B&H 미달. DCA+MeanRev 하이브리드 추천 |
| 2026-03-06 | backtest | Sell-Timing 파라미터 그리드 서치 | [링크](backtest/2026-03-06-sell-timing-grid-search.md) | 38종목x240조합. 1y 97% 승률, full 34%. Best: RSI>65+SMA200→RSI<25. 레버리지ETF에서 가장 효과적 |
| 2026-03-07 | backtest | 매크로 레짐 감지 | [링크](backtest/2026-03-07-macro-regime-detection.md) | 구리/유가/VIX/금/금리/달러 레짐. 4쌍x240조합. B&H 3x 승률 0~2%. TNA만 +474%. MaxDD 15~25%p 개선 |
| 2026-03-07 | backtest | 매크로 레짐 + RSI 결합 | [링크](backtest/2026-03-07-macro-regime-rsi-combined.md) | 레짐을 필터로 활용. SOXL +385,753%(90B/89S). filter_block+force가 SPXL/TNA에서 압도. confirm=10d 최적 |
| 2026-03-07 | backtest | 매크로 레짐 심층 분석 | [링크](backtest/2026-03-07-macro-regime-deep-analysis.md) | OOS: SOXL 과적합(0%), TNA만 유효(+117%). Ablation: oil+tnx 최강, copper/gold 무효. 실전: 종목별 다른 전략 필요 |
| 2026-03-07 | backtest | 7가지 추가 실험 종합 | [링크](backtest/2026-03-07-seven-experiments.md) | BB+RSI 평균 +2,542% 1위. 8~9월 회피가 B&H 능가. Vol target MaxDD 30~50%p 개선. 3x ETF 상관 높아 분산 제한 |
| 2026-03-07 | backtest | OOS 검증: VIX Term + ATR Sizing | [링크](backtest/2026-03-07-oos-validation-vix-atr.md) | VIX term: 4종목 중 3개 FAIL(과적합). ATR sizing: all-in 최적, QLD만 OOS 통과(+27%p). 두 전략 모두 조언용으로만 반영 |
| 2026-03-07 | backtest | 5가지 추가 실험 + 실전 시뮬 | [링크](backtest/2026-03-07-five-additional-experiments.md) | 89회피+BB결합 시너지없음. 수수료 둔감(거래적음). VIX스케일링 MaxDD개선. 실전시뮬: TNA/UWM만 B&H초과, 강세장서 타이밍전략 열위 |
| 2026-03-07 | backtest | 7가지 심층 실험 (41종목) | [링크](backtest/2026-03-07-seven-deep-experiments.md) | 오버나이트 수익 90%+. 금리상승기 30/41종목 강세. 트레일링스탑 레버리지불가. 120일보유≈RSI청산. 추가정보는 노이즈, 현행 유지 |
| 2026-03-07 | backtest | Alert 전략 11개 대안 비교 | [링크](backtest/2026-03-07-alert-strategy-comparison.md) | baseline Sharpe 0.765 최고. 11개 대안 전부 열위. 나스닥 regime_sma200만 shadow 모니터링 가치 |
| 2026-03-07 | backtest | Alert.py 최적화 + OOS 검증 | [링크](backtest/2026-03-07-alert-optimization-oos.md) | 16,800조합+106 rolling OOS. sell+sma200 승률 24% FAIL. 현행 유지 최적 |
| 2026-03-07 | backtest | 현행 Alert vs B&H 종합 비교 | [링크](backtest/2026-03-07-alert-bh-comparison.md) | 수익률은 B&H 우세(5/7). 전략 가치는 폭락 방어(MaxDD -89%→-32%). 매수 타이밍만 활용 분석 예정 |
| 2026-03-07 | backtest | 3인 전문가 팀 백테스트 종합 | [링크](backtest/2026-03-07-expert-team-backtest.md) | 소형주만 RSI 유효(TNA +2364%p). 대형3x는 B&H 압도. TNA BB필터 적용(Bear -21%→+18%). VIX스케일링/시간손절 부정 |
| 2026-03-07 | backtest | 혼합 포트폴리오 OOS 검증 | [링크](backtest/2026-03-07-portfolio-oos-validation.md) | SPXL40+GLD60 band5 OOS +320%(vs B&H +228%). Rolling OOS 90% 승률. MaxDD -41%(vs -77%). 도입 추천 |
| 2026-03-07 | backtest | 자산배분 188만 조합 3인 전문가 분석 | [링크](backtest/2026-03-07-asset-allocation-grid-188m.md) | 레버리지10%+GLD90%+quarterly가 최적(Sharpe1.44,MDD-18%). 현행alert(MDD-56%)보다 수익↑위험↓. 5년데이터 과적합 경고 |
| 2026-03-07 | backtest | 5가지 그리디 전수 탐색 (743K조합) | [링크](backtest/2026-03-07-greedy-five-experiments.md) | 포트폴리오: NVDA20+GLD80 Sharpe 1.76. DCA: RSI가중 94.8%승률. 듀얼모멘텀/DD매수/리드래그 폐기 |
| 2026-03-07 | backtest | 에너지x기술 크로스섹터 (398K건) | [링크](backtest/2026-03-07-energy-cross-sector-backtest.md) | DCA Sharpe 3.4(WF100%통과). XOM+NVDA+GLD+BND 4자산 Sharpe 1.87,MDD-20%. 금급등→NVDA 거래11건 통계불충분 |
