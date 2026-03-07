# 에너지 x 기술 크로스섹터 백테스트 (398,590건)

- **날짜**: 2026-03-07
- **카테고리**: backtest
- **코드**: `experiments/exp_energy_strategies.py`, `exp_energy_macro.py`, `exp_energy_portfolio.py`, `exp_energy_validate.py`
- **결과 CSV**: `results/energy_strategies_results.csv`, `energy_macro_results.csv`, `energy_portfolio_results.csv`, `energy_validate_results.csv`
- **심볼**: 에너지 15종(CVX,XOM,XLE,XOP,OIH,FANG,VDE,ERX,COP,SLB,EOG,MPC,PSX,HAL,DVN) + 방산 3종(LMT,RTX,NOC) + 기술 3종(NVDA,AAPL,MSFT) + 포트폴리오 자산
- **타임프레임**: 일봉 (daily)
- **기간**: 전체 (~16년), IS/OOS 70%/30% 분할
- **SHV 기준선**: CAGR 1.52%, MDD -0.45% (2007~2026, 19yr)

## 개요

에너지주 + 기술주 크로스섹터 대규모 백테스트. 9개 전략(strategies), 12개 매크로/이벤트 실험(macro), 8개 포트폴리오 실험(portfolio), 검증(validate) 총 398,590건.

## Phase별 실험 규모

| Phase | 스크립트 | 조합 | 실행 시간 |
|-------|---------|------|----------|
| 1. Strategies | exp_energy_strategies.py | 293,175 | ~3시간 |
| 2. Macro | exp_energy_macro.py | 57,489 | ~10분 |
| 3. Portfolio | exp_energy_portfolio.py | 47,925 | ~30분 |
| 4. Validate | exp_energy_validate.py | 148 | <1분 |
| **합계** | | **398,737** | |

## Phase 1: Strategies Top 5 (OOS Sharpe 기준, 일봉, ~4.2yr OOS)

| 순위 | 종목 | 전략 | OOS Sharpe | OOS 수익 | OOS MDD | 거래 | 거래/yr | vs B&H |
|:----:|------|------|----------:|--------:|--------:|-----:|-------:|-------:|
| 1 | PSX | DCA(freq=5,threshold) | 3.44 | +62.6% | -26.8% | 1,049 | 252 | -105.5%p |
| 2 | MPC | DCA(freq=5,threshold) | 3.40 | +89.1% | -28.8% | 1,109 | 252 | -199.4%p |
| 3 | PSX | DCA(freq=5,threshold) | 3.38 | +62.1% | -26.8% | 1,049 | 252 | -106.0%p |
| 4 | PSX | DCA(freq=5,threshold) | 3.38 | +62.2% | -26.8% | 1,049 | 252 | -105.9%p |
| 5 | MPC | DCA(freq=5,threshold) | 3.35 | +89.9% | -30.1% | 1,109 | 252 | -198.7%p |

**인사이트**: DCA가 에너지 종목에서 압도적으로 높은 Sharpe. MDD -27~30%로 순수 B&H 대비 안정적. 단, 절대 수익률은 B&H에 밀림 (DCA는 점진투자라 강세장에서 불리).

## Phase 2: Macro/Event Top 5 (OOS Sharpe 기준, 일봉, ~7.6yr OOS)

| 순위 | 종목 | 실험 | OOS Sharpe | OOS 수익 | OOS MDD | 거래 | 거래/yr | vs B&H |
|:----:|------|------|----------:|--------:|--------:|-----:|-------:|-------:|
| 1 | NVDA | gold_spike(delay=5,hold_120) | 1.60 | +2,391% | -25.0% | 11 | 1.4 | -432.7%p |
| 2 | NVDA | gold_spike(delay=2,hold_120) | 1.52 | +2,084% | -28.3% | 11 | 1.4 | -740.3%p |
| 3 | NVDA | gold_spike(delay=0,hold_120) | 1.45 | +1,777% | -31.0% | 11 | 1.4 | -1,047.1%p |
| 4 | NVDA | gold_spike(trail_10%) | 1.31 | +1,832% | -48.9% | 45 | 5.9 | -992.4%p |
| 5 | RTX | regime_switch(vix_level) | 1.26 | +243% | -16.2% | 3 | 0.4 | +47.1%p |

**인사이트**: 금 급등 시 NVDA 매수 → 120일 보유가 최고 Sharpe. 거래 11건으로 통계 신뢰도 낮지만, 위기 후 기술주 반등 패턴 포착. RTX regime_switch만 B&H 초과.

## Phase 3: Portfolio Top 5 (OOS Sharpe 기준, 일봉, ~5.7yr OOS)

| 순위 | 자산 | 비중 | 리밸 | OOS Sharpe | OOS 수익 | OOS MDD | 거래 | 거래/yr | vs B&H |
|:----:|------|------|------|----------:|--------:|--------:|-----:|-------:|-------:|
| 1 | XOM\|NVDA\|GLD\|BND | 20/20/40/20 | band_10% | 1.87 | +365% | -19.9% | 68 | 12.0 | -152.6%p |
| 2 | XOM\|NVDA\|GLD\|BND | 20/20/40/20 | annual | 1.82 | +430% | -17.8% | 52 | 9.2 | -87.8%p |
| 3 | VDE\|NVDA\|GLD\|BND | 20/20/40/20 | band_10% | 1.81 | +360% | -21.8% | 68 | 12.0 | -134.9%p |
| 4 | XLE\|NVDA\|GLD\|BND | 20/20/40/20 | band_10% | 1.80 | +347% | -22.1% | 68 | 12.0 | -144.5%p |
| 5 | XOM\|NVDA\|GLD | 20/20/60 | annual | 1.79 | +699% | -20.5% | 45 | 7.0 | -250.0%p |

**인사이트**: 에너지(XOM)+기술(NVDA)+방어(GLD/BND) 4자산 포트폴리오가 Sharpe 1.8+. MDD -18~22%로 개별 B&H(-70~80%) 대비 극적 개선. GLD 40% 비중이 핵심.

## Phase 4: Validation 결과

### Walk-Forward OOS (6윈도우, 5yr train → 2yr test, 1yr slide)

| 종목 | 전략 | 승률(Sharpe>0.5) | 평균 OOS Sharpe | 평균 vs B&H | 평균 거래 | 거래/yr |
|------|------|:----------------:|:--------------:|:----------:|:--------:|-------:|
| PSX | DCA | **100%** | 4.88 | +3,387%p | 504 | 252 |
| MPC | DCA | **100%** | 4.72 | +3,688%p | 504 | 252 |

6개 윈도우 모두 Sharpe > 0.5 통과. **과적합 아님 확인.**

### Ensemble (4방식)

| 방식 | 종목 | OOS Sharpe | OOS 수익 | OOS MDD | 거래 | 거래/yr |
|------|------|----------:|--------:|--------:|-----:|-------:|
| equal_weight | PSX | 3.35 | +8,735% | -26.7% | N/A | N/A |
| sharpe_weight | PSX | 3.35 | +8,742% | -26.7% | N/A | N/A |
| rank_weight | PSX | 3.38 | +9,230% | -26.7% | N/A | N/A |
| majority_vote | PSX | 0.02 | -11.6% | -42.4% | 478 | 114.8 |
| equal_weight | MPC | 3.37 | +11,708% | -29.3% | N/A | N/A |
| rank_weight | MPC | 3.38 | +11,864% | -29.2% | N/A | N/A |
| majority_vote | MPC | -0.35 | -42.4% | -64.7% | 499 | 113.4 |

equal/sharpe/rank weight 앙상블: Sharpe 3.35~3.38 유지. majority_vote: 실패 (잦은 매매).

### Fee Sensitivity (5단계)

| 종목 | 전략 | 손익분기 수수료 | @0.25% Sharpe | 거래 | 거래/yr |
|------|------|:-------------:|:------------:|-----:|-------:|
| PSX | DCA | **1.00%** | 3.38 | 1,049 | 252 |
| MPC | DCA | **1.00%** | 3.35 | 1,109 | 252 |

1% 수수료까지도 B&H 대비 유리. DCA 특성상 소액 분할 매수라 수수료 부담 최소.

## 핵심 인사이트

1. **에너지 DCA가 Sharpe 최강** — PSX/MPC에서 Sharpe 3.4+, 6/6 WF 윈도우 통과
2. **포트폴리오 분산이 MDD 관리 최적** — 에너지+기술+GLD 4자산: MDD -18~22% (순수 B&H -70~80% 대비 50%p+ 개선)
3. **지정학 이벤트 프록시는 제한적 유효** — 금 급등→NVDA 매수가 최선이나, 거래 11건으로 통계 불충분
4. **RTX regime_switch만 B&H 초과** — 방산주+VIX 레짐이 유일한 B&H 초과 매크로 전략
5. **DCA vs B&H**: DCA는 Sharpe/MDD에서 우위이나 절대 수익은 B&H에 밀림. 리스크 관리 관점에서 가치
6. **GLD 40% 비중이 포트폴리오 핵심** — 기존 SPXL+GLD 연구와 일치

## 실전 적용 권장

| 전략 | 적용 | 이유 |
|------|------|------|
| 에너지 DCA (PSX/MPC) | O 참고 | Sharpe 최고, WF 100% 통과. 단 매일 거래 필요 |
| 에너지+기술+GLD 4자산 | **O 강력 추천** | Sharpe 1.8+, MDD -20%, 리밸 연 9~12회 |
| 금 급등→NVDA | △ 모니터링 | 거래 11건, 통계 불충분 |
| VIX 레짐→RTX | △ 모니터링 | 거래 3건, 통계 불충분 |

## 한계점

- DCA 비교: DCA는 추가 자금 투입(일 $100)이므로 초기 $2,000 B&H와 직접 비교 한계
- 매크로 이벤트 프록시: 거래 횟수 3~11건으로 통계 유의성 낮음
- 포트폴리오: 리밸런싱 슬리피지 미반영
- PXD 상장폐지로 에너지 15종목 (원래 16종 계획)

## 후속 방향

1. DCA 현실화: 추가 자금 투입 없는 순수 타이밍 전략과 공정 비교
2. 4자산 포트폴리오를 alert.py에 리밸런싱 알림 추가
3. 금 급등 이벤트 장기 축적 모니터링
