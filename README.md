# Stock Bot

레버리지 ETF 매매 시그널 봇 + 백테스트 프레임워크.

## 구조

```
alert.py              # 텔레그램 매매 시그널 봇 (매일 cron)
download.py           # yfinance 데이터 다운로드 → parquet
config.py             # 심볼, 수수료, 프리셋
backtest/
  engine.py           # 백테스트 엔진 (단일/포트폴리오/fast)
  strategies/
    bb_rsi_ema.py     # BB + RSI + EMA 평균회귀 전략
  grid_search.py      # 파라미터 그리드 서치 (멀티프로세스, JSON 캐시)
  metrics.py          # Sharpe, Calmar, MaxDD 등
  data_loader.py      # parquet 로드 (daily/weekly/hourly)
  report_html.py      # HTML 리포트 생성
  runner.py           # CLI 진입점
analysis/             # 실험 결과 기록
  INDEX.md
data/                 # 가격 데이터 (parquet)
tests/                # 177개 테스트
```

## 봇 (alert.py)

RSI 기반 매수/매도/재매수 시그널을 텔레그램으로 전송.

| 종목 | 그룹 | Buy RSI | Sell RSI | 비고 |
|------|------|:---:|:---:|------|
| SOXL | 3x 반도체 | 25 | 60 | |
| TQQQ | 3x 나스닥 | 25 | 65 | |
| SPXL | 3x S&P500 | 30 | 70 | |
| TNA | 3x 소형주 | 35 | 70 | 구리 필터 |
| QLD | 2x 나스닥 | 25 | 70 | ATR 사이징 |
| UWM | 2x 소형주 | 25 | 70 | 구리 필터 |
| QQQ | 나스닥100 | 25 | 75 | |
| GGLL | 2x 구글 | 30 | - | buy only |
| NVDA | 엔비디아 | 35 | - | buy only |

추가 기능: VIX term structure, 구리 SMA 필터, ATR 포지션 사이징, 8~9월 경고

## 실험 총정리

총 **30종류 실험**, 약 **4,500만 개 파라미터 조합** 평가.

### 백테스트 실험 목록

| # | 실험 | 대상 | 조합 수 | 핵심 결과 |
|---|------|------|--------:|----------|
| 1 | SOXL 임계값 전략 (시간봉 TP/SL) | SOXL | 216 | 1%/1%/1% = -97%. Best: 1.5%/3%/5% = +60%. 비대칭 TP/SL 필수 |
| 2 | SOXL 매수 타이밍 (17개 전략) | SOXL | 17 | B&H +9,020% 압도. 타이밍 전략 모두 B&H 미달. DCA+MeanRev 하이브리드 추천 |
| 3 | Sell-Timing 그리드 서치 | 38종목 | 9,120 | 1y 97% 승률, full 34%. RSI>65+SMA200 → RSI<25 재매수가 최적 |
| 4 | 매크로 레짐 감지 | 4쌍 | 960 | 구리/유가/VIX/금/금리/달러. B&H 승률 0~2%. TNA만 +474% |
| 5 | 매크로 레짐 + RSI 결합 | 4쌍 | 1,680 | 레짐을 필터로 활용 시 극적 개선. SOXL +385,753%. confirm=10d 최적 |
| 6 | 매크로 레짐 심층 (OOS+Ablation) | 4쌍 | ~200 | OOS: SOXL 과적합(0%), TNA만 유효. oil+tnx 최강, copper/gold 무효 |
| 7 | Walk-Forward Analysis | 4종목 | ~80 | MaxDD 대폭 개선(SOXL -89%→-32%). 수익률은 B&H 미달 |
| 8 | Volatility Targeting | 4종목 | ~80 | MaxDD 30~53%p 개선. target_vol=30%, window=21d 공통 최적 |
| 9 | Drawdown-Based Entry | 4종목 | ~60 | 분할매수 B&H 미달. conservative+trail=15%가 risk-adjusted 양호 |
| 10 | Correlation Portfolio | 4종목 | ~20 | 3x ETF 간 상관 0.76~0.93. 분산 효과 없음 |
| 11 | Regime Strategy Switching | 4종목 | ~80 | SOXL에서만 스위칭 유효. 나머지는 BB+RSI 단독이 우수 |
| 12 | Seasonality (계절성) | 4종목 | 20 | 8~9월 회피가 4종목 모두 B&H 능가. Sell in May 부진 |
| 13 | Strategy Benchmark (5개 전략) | 4종목 | 20 | BB+RSI+EMA 평균 +2,542%로 1위. 다른 전략의 10배 이상 |
| 14 | 트레일링 스탑 최적화 | 41종목 | 205 | 레버리지에는 스탑 불필요 (변동성 과다). 개별주에만 T20% 유효 |
| 15 | 레버리지 디케이 정량화 | 4쌍 | 4 | SOXL/SOXX 연 -72.3% 디케이. 3x ETF 기대수익 90%+ 소멸 |
| 16 | 멀티타임프레임 RSI | 41종목 | 41 | 41종목 중 11개만 MTF 우위. 대부분 Daily가 나음 |
| 17 | 보유 기간 분석 | 41종목 | 246 | 120일 보유 17/41 우승, RSI 청산 15/41. 현행 RSI 청산 유지 |
| 18 | 오버나이트 vs 장중 수익률 | 41종목 | 41 | 수익의 90%+가 오버나이트 발생. 장중 매매 불필요 |
| 19 | 금리 레짐별 성과 | 41종목 | 41 | 30/41 종목 금리 상승기 강세. 실시간 의사결정에는 불충분 |
| 20 | 드로다운 회복 속도 | 41종목 | 41 | 레버리지: 빈번하지만 빠른 회복. 지수: 드물지만 느린 회복 |
| 21 | 8~9월 회피 + BB+RSI 결합 | 4종목 | 4 | 시너지 없음. 독립 사용이 더 나음 |
| 22 | 수수료 민감도 분석 | 4종목 | 12 | 거래 적어 1%까지 견딤. 수수료보단 전략 자체가 문제 |
| 23 | VIX B&H 포지션 조절 | 4종목 | 4 | 리밸런싱 240~461회, 수수료로 수익 소멸 |
| 24 | VIX + BB+RSI 스케일링 | 4종목 | 4 | MaxDD 개선 효과. conservative(VIX<20:100%, >25:0%) |
| 25 | alert.py 실전 시뮬 (2023~현재) | 7종목 | 7 | 강세장서 B&H 우세. TNA/UWM만 B&H 초과 |
| 26 | VIX Term Structure OOS | 4종목 | 100 | 4종목 중 3종목 FAIL(과적합). 자동 시그널 부적합 |
| 27 | ATR Position Sizing OOS | 7종목 | 105 | all-in 최적. QLD만 OOS 통과. 리스크 관리용 |
| 28 | 계절성 통계적 유의성 (부트스트랩) | 6종목 | ~60,000 | SPY만 p=0.047. 레버리지 8~9월 효과는 통계적 비유의 |
| 29 | BB+RSI+EMA 전체 그리드 서치 | 41종목 | 41,237,328 | buy_rsi=25 보수적 값이 OOS 안전. 현행 유지 |
| 30 | 자산배분 그리드 서치 (진행중) | 11종목 | 1,885,950 | 공격(레버리지)+방어(ETF) 포트폴리오, 리밸런싱 주기/밴드 |

### 핵심 결론

**전략:**
- BB+RSI+EMA가 레버리지 ETF 최적 전략 (다른 전략 대비 10배+ 수익)
- 보수적 RSI 임계값(buy<25)이 OOS에서도 안전하게 작동
- 8~9월 회피가 가장 실용적 알파 (파라미터 프리, 구현 간단)

**시장 구조:**
- 수익의 90%+가 오버나이트에 발생 → 종가 매수/보유가 정답
- 강세장에서는 어떤 타이밍 전략도 B&H를 못 이김
- 소형주(TNA/UWM)만 타이밍 전략이 B&H 초과

**리스크:**
- 3x ETF 연간 디케이 25~72% → 장기 보유 불리
- Volatility Targeting이 MaxDD 30~50%p 개선 (수익 희생)
- 3x ETF 간 상관 0.76~0.93 → 포트폴리오 분산 효과 없음

**과적합 경고:**
- 매크로 레짐, VIX term, ATR sizing 모두 OOS 대부분 FAIL
- in-sample 최적 ≠ 미래 최적. 단순한 전략이 robust
- "행동으로 연결 안 되는 정보는 추가하지 말자"

## 사용법

```bash
# 데이터 다운로드
python download.py

# 백테스트
python -m backtest.runner --symbol SOXL --period 5y

# 그리드 서치
python -m backtest.runner --grid --symbols SOXL TQQQ --periods 1y 3y 5y

# 알림 봇 실행
python alert.py

# 테스트
pytest tests/ -v
```

## 환경

- Python 3.14
- 의존성: yfinance, pandas, numpy, python-dotenv
- 텔레그램 봇: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` (.env)
