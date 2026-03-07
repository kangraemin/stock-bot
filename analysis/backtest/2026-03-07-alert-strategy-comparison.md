# Alert 전략 11개 대안 비교 백테스트

- 날짜: 2026-03-07
- 백테스트 코드: `alert_backtest_compare.py`
- 결과 CSV: `results/alert_strategy_compare.csv`
- **타임프레임**: 일봉 (daily)
- **분석 기간**: 전체 (~16년)
- **SHV 기준선**: CAGR 1.52%, MDD -0.45% (2007~2026, 19yr)

## 개요

현재 alert.py의 RSI+BB 전략(baseline)을 포함한 11개 전략을 6개 alert 종목에서 동일 조건으로 백테스트하고, 퀀트/리스크매니저/실전트레이더 3인 팀 토론으로 결론 도출.

## 테스트 전략 (11개)

| # | 전략 | 매수 조건 | 매도 조건 |
|---|---|---|---|
| 1 | **baseline** (현행) | RSI(14) < buy_rsi | RSI > sell_rsi AND close > BB상단 |
| 2 | bb_lower_buy | RSI < buy_rsi AND close < BB하한 | baseline과 동일 |
| 3 | regime_sma200 | RSI < buy_rsi AND close > SMA(200) | baseline과 동일 |
| 4 | trailing_stop | RSI < buy_rsi | ATR(14) x2.5 트레일링스탑 |
| 5 | macd_confirm | RSI < buy_rsi AND MACD_diff > 0 | baseline과 동일 |
| 6 | wider_rsi | RSI < (buy_rsi-5) | RSI > (sell_rsi+5) AND close > BB상단 |
| 7 | rsi7_fast | RSI(7) < buy_rsi | RSI(7) > sell_rsi AND close > BB상단 |
| 8 | bb_pctb | BB %B < 0 | BB %B > 1 |
| 9 | regime+trailing | RSI < buy_rsi AND close > SMA(200) | ATR 트레일링스탑 OR close < SMA(200) |
| 10 | stoch_rsi | StochRSI K < 0.1 | StochRSI K > 0.9 AND close > BB상단 |
| 11 | sell_bb_only | RSI < buy_rsi | close > BB상단 (RSI 조건 제거) |

## 파라미터 / 대상 종목

| 종목 | buy_rsi | sell_rsi | rebuy_rsi |
|---|---|---|---|
| SOXL | 25 | 60 | 55 |
| TQQQ | 25 | 65 | 55 |
| SPXL | 30 | 70 | 55 |
| TNA | 35 | 70 | 50 |
| QLD | 25 | 70 | 55 |
| QQQ | 25 | 75 | 55 |

## 결과 요약 (전체 평균)

> **vs B&H 참고**: 6개 종목의 B&H 수익률이 종목별로 상이하므로, 전체 평균 테이블에서는 baseline(현행 전략) 대비 초과/미달 수익률(%p)로 비교.

| Strategy | Return | vs baseline | Ann.Ret | MaxDD | Sharpe | Calmar | Trades | Trades/yr |
|---|---|---|---|---|---|---|---|---|
| **baseline** | 18,354% | — | 28.9% | -75.9% | **0.765** | 0.371 | 93 | 5.8 |
| sell_bb_only | 16,807% | -1,547%p | 26.9% | -75.6% | 0.727 | 0.344 | 185 | 11.6 |
| bb_lower_buy | 5,652% | -12,702%p | 23.4% | -70.6% | 0.693 | 0.324 | 57 | 3.6 |
| rsi7_fast | 14,203% | -4,151%p | 25.4% | -79.7% | 0.689 | 0.316 | 191 | 11.9 |
| stoch_rsi | 2,994% | -15,360%p | 19.3% | -80.2% | 0.607 | 0.241 | 148 | 9.3 |
| regime_sma200 | 4,603% | -13,751%p | 18.4% | -57.1% | 0.598 | 0.267 | 61 | 3.8 |
| trailing_stop | 2,838% | -15,516%p | 18.0% | -81.5% | 0.587 | 0.217 | 335 | 20.9 |
| wider_rsi | 2,038% | -16,316%p | 15.2% | -58.2% | 0.535 | 0.216 | 22 | 1.4 |
| bb_pctb | 1,456% | -16,898%p | 14.9% | -79.2% | 0.523 | 0.186 | 118 | 7.4 |
| regime+trailing | 910% | -17,444%p | 10.1% | -42.9% | 0.455 | 0.208 | 209 | 13.1 |
| macd_confirm | 497% | -17,857%p | 3.7% | -10.5% | 0.112 | 0.058 | 6 | 0.4 |

## 종목별 baseline 상회 전략 (*** 표시)

| 종목 | 전략 | baseline Sharpe | 대안 Sharpe | MDD 개선 |
|---|---|---|---|---|
| TQQQ | regime_sma200 | 0.810 | **0.829** | -78.8% -> -71.3% |
| SPXL | sell_bb_only | 0.853 | **0.904** | 동일 |
| TNA | macd_confirm | 0.619 | **0.673** | -84.5% -> -62.9% |
| TNA | wider_rsi | 0.619 | **0.658** | 동일 |
| TNA | bb_lower_buy | 0.619 | **0.654** | -84.5% -> -82.3% |
| QQQ | wider_rsi | 0.623 | **0.682** | -51.3% -> -52.0% |
| QQQ | regime_sma200 | 0.623 | **0.671** | -51.3% -> -33.9% |
| SOXL | - | 0.938 (최고) | - | - |
| QLD | - | 0.746 (최고) | - | - |

## 핵심 인사이트 (3인 팀 토론)

### 1. Baseline이 전체 평균 최고 - 변경 불필요
- 평균 Sharpe 0.765로 11개 전략 중 1위
- 종목별로 이기는 전략이 있으나, 일관성이 없어 과적합 위험

### 2. 나스닥100 계열에서 regime_sma200이 구조적으로 유효할 가능성
- TQQQ + QQQ (동일 기초지수) 2종목에서 일관 상회
- SMA(200) 필터가 하락장 물타기를 방지하는 구조적 효과
- MDD -75.9% 회복에 +315% 필요 vs -57.1%는 +133%로 회복 난이도 절반

### 3. 폐기 사유 정리
- **거래 부족**: macd_confirm(6회), wider_rsi(22회) - 최소 30회 미달
- **수익 희생 과대**: regime+trailing - MDD -42.9%이나 Ann.Ret 10.1% (SPY B&H 수준)
- **1종목 과적합**: sell_bb_only(SPXL만), bb_lower_buy(TNA만)
- **전면 열위**: trailing_stop, stoch_rsi, bb_pctb, rsi7_fast

### 4. 운영 리스크
- 수동 매매 환경에서 종목별 복수 전략은 사용자 혼동 유발
- 단일 전략 유지가 운영 안전성 확보

## 제안사항 (3인 합의)

### 즉시 적용 (리스크 제로)
- 알림에 "SMA200 하회 중" 참고 정보 표시 추가 (매매 로직 변경 없음)

### Shadow 모니터링 (12개월)
- TQQQ/QQQ: regime_sma200 신호 별도 기록
- SPXL: sell_bb_only 신호 별도 기록
- baseline과 신호가 다를 때만 기록
- 하락장 1회 포함 OOS 검증 후 재논의

## 한계점
- 수수료 0.25% 고정 (실전 변동 없음)
- 슬리피지 미반영
- 매크로 필터(구리, VIX) 미포함 백테스트
- 데이터 기간이 주로 상승장 포함 (생존 편향 가능)

## 후속 방향
1. SMA200 참고 정보를 alert.py 알림에 추가
2. shadow 모드 구현 (.states/shadow_regime.json)
3. 12개월 후 shadow 결과 기반 재평가
