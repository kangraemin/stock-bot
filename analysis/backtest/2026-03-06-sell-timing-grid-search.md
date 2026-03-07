# Sell-Timing Parameter Grid Search (개별 종목 최적 파라미터)

- **날짜**: 2026-03-06 21:40
- **카테고리**: backtest
- **커맨드**: /analyze grid (custom sell-timing)
- **심볼**: 38종목 (NASDAQ 10 + S&P500 10 + Indices 6 + 2x Lev 5 + 3x Lev 7)
- **타임프레임**: daily
- **분석 기간**: 1y / 3y / 5y / 10y / full (최대 ~16년)
- **SHV 기준선**: CAGR 1.52%, MDD -0.45% (2007~2026, 19yr)
- **소요시간**: 43초

## 요약

38개 심볼 x 5개 기간 x 240개 파라미터 조합 (총 45,600 반복) 그리드 서치.
**단기(1y)에서는 97%가 B&H를 이기지만, 장기(10y+)에서는 29~34%만 이김.**
최적 유니버설 패턴: `Sell RSI>65 + 가격>SMA200 → Rebuy RSI<25`.

## 파라미터 그리드

| 파라미터 | 값 |
|---------|-----|
| Sell RSI 임계값 | 65, 70, 75, 80 |
| Rebuy RSI 임계값 | 25, 30, 35, 40, 45 |
| Sell 조건 | rsi_only, rsi+bb, rsi+sma50, rsi+sma200 |
| Rebuy 조건 | rsi_only, rsi+bb, rsi+sma50 |
| **총 조합** | **4 x 5 x 4 x 3 = 240** |
| 수수료 | 0.25% + 슬리피지 0.1% |

## 기간별 B&H 승률

| 기간 | B&H 이긴 심볼 | 승률 |
|------|-------------|------|
| **1y** | 37/38 | **97%** |
| **3y** | 28/38 | 74% |
| **5y** | 27/38 | 71% |
| **10y** | 11/38 | 29% |
| **full** | 13/38 | 34% |

## 가장 효과적인 파라미터 (B&H 이긴 경우만)

### Sell RSI 임계값
| RSI 임계값 | 빈도 |
|-----------|------|
| RSI>65 | 45회 |
| RSI>70 | 33회 |
| RSI>80 | 21회 |
| RSI>75 | 17회 |

### Rebuy RSI 임계값
| RSI 임계값 | 빈도 |
|-----------|------|
| RSI<25 | 26회 |
| RSI<45 | 25회 |
| RSI<30 | 23회 |
| RSI<35 | 22회 |
| RSI<40 | 20회 |

### Sell 조건 (보조 필터)
| 조건 | 빈도 |
|-----|------|
| **rsi+sma200** | **55회** |
| rsi+sma50 | 25회 |
| rsi_only | 21회 |
| rsi+bb | 15회 |

### Rebuy 조건
| 조건 | 빈도 |
|-----|------|
| **rsi_only** | **67회** |
| rsi+sma50 | 28회 |
| rsi+bb | 21회 |

## Top 10 Winning Combos (전체 심볼/기간에서 가장 자주 이긴 파라미터 세트)

| Rank | Sell | Sell조건 | Rebuy | Rebuy조건 | 빈도 |
|------|------|---------|-------|----------|------|
| 1 | RSI>65 | rsi+sma200 | RSI<25 | rsi_only | 8회 |
| 2 | RSI>65 | rsi+sma200 | RSI<45 | rsi_only | 7회 |
| 3 | RSI>65 | rsi+sma200 | RSI<30 | rsi_only | 6회 |
| 4 | RSI>65 | rsi+sma200 | RSI<35 | rsi+sma50 | 5회 |
| 5 | RSI>65 | rsi+sma200 | RSI<40 | rsi_only | 5회 |
| 6 | RSI>65 | rsi+sma50 | RSI<25 | rsi_only | 5회 |
| 7 | RSI>70 | rsi+sma200 | RSI<25 | rsi_only | 4회 |
| 8 | RSI>70 | rsi+sma200 | RSI<45 | rsi+bb | 4회 |
| 9 | RSI>65 | rsi+sma200 | RSI<30 | rsi+sma50 | 4회 |
| 10 | RSI>80 | rsi+sma200 | RSI<25 | rsi_only | 3회 |

> *거래횟수(trades/yr)는 종목/기간별로 상이하여 파라미터 우승 빈도만 표시. 개별 거래횟수는 기간별 Top 5 참조.*

## 기간별 Top 5 (vs B&H)

> *그리드서치 결과로 개별 거래횟수(trades/yr) 데이터가 포함되지 않음. 거래 빈도는 RSI 임계값과 종목 변동성에 따라 상이.*

### 1y (37/38 이김)
| Sym | Group | Sell RSI | Sell조건 | Rebuy RSI | Rebuy조건 | 전략 | B&H | vs BH |
|-----|-------|---------|---------|----------|----------|------|-----|-------|
| SOXL | 3x Lev | 65 | rsi+sma200 | 25 | rsi_only | +65% | -46% | +111%p |
| TNA | 3x Lev | 65 | rsi+sma200 | 45 | rsi_only | +25% | -20% | +45%p |
| TECL | 3x Lev | 65 | rsi+sma200 | 30 | rsi_only | +35% | -5% | +40%p |
| FNGU | 3x Lev | 65 | rsi_only | 45 | rsi_only | +38% | +2% | +36%p |
| UWM | 2x Lev | 65 | rsi+sma200 | 45 | rsi+sma50 | +10% | -18% | +28%p |

### full period (13/38 이김)
| Sym | Group | Sell RSI | Sell조건 | Rebuy RSI | Rebuy조건 | 전략 | B&H | vs BH |
|-----|-------|---------|---------|----------|----------|------|-----|-------|
| SOXL | 3x Lev | 80 | rsi+sma200 | 25 | rsi_only | +4,567% | +1,230% | +3,337%p |
| TNA | 3x Lev | 70 | rsi+sma200 | 30 | rsi+bb | +230% | +15% | +215%p |
| SPXL | 3x Lev | 65 | rsi+sma200 | 25 | rsi_only | +2,100% | +1,950% | +150%p |

## 핵심 인사이트

1. **단기일수록 sell-timing이 유효** — 1y에서 97% 승률이지만 full period에서는 34%로 급감
2. **SMA200 필터가 핵심** — 매도 시 "가격이 SMA200 위에 있을 때만" 매도하면 불필요한 조기 매도를 막음
3. **재매수는 RSI만으로 충분** — 추가 필터 없이 RSI<25~45에서 재매수하는 게 가장 효과적
4. **3x 레버리지 ETF에서 가장 효과적** — SOXL, TNA, TECL, FNGU에서 압도적 성과
5. **일반 대형주(AAPL, MSFT 등)는 장기 B&H가 우세** — 최적 파라미터로도 10년 이상은 B&H 승리
6. **개별 종목마다 최적 파라미터가 크게 다름** — 유니버설 파라미터는 존재하지 않음

## 결론

- **레버리지 ETF 매매**: `RSI>65 + 가격>SMA200`에서 매도 → `RSI<25`에서 재매수 추천
- **일반주/인덱스**: 매도 타이밍보다 B&H가 장기적으로 유리. 단기 트레이딩 시에만 유효
- **실전 적용 시 주의**: 1y 백테스트 과적합(overfitting) 가능성 높음. Out-of-sample에서는 SOXL/TNA만 일관성 있음
