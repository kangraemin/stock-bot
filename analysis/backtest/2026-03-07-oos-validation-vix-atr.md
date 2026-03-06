# OOS 검증: VIX Term Structure + ATR Position Sizing

- **날짜**: 2026-03-07
- **카테고리**: backtest
- **커맨드**: exp5_vix_term_oos.py, exp2_atr_sizing_oos.py
- **심볼**: SOXL, TQQQ, SPXL, TNA, QLD, UWM, QQQ
- **분할**: train < 2020, test >= 2020

## 요약

- **ATR Position Sizing**: 7종목 중 6종목에서 all-in(risk=1.0)이 train best → OOS에서 차이 없음. QLD만 유일하게 OOS 통과 (+26.6%p, MaxDD -14%p 개선)
- **VIX Term Structure**: train best → test 적용 시 4종목 중 3종목 FAIL. SPXL만 소폭 통과 (+14.1%). test actual best는 매우 높지만 train에서 선택 불가 (과적합)
- **결론**: 두 전략 모두 자동 시그널 변경에는 부적합. alert.py에 정보 제공 + 포지션 사이징 조언으로 반영

---

## 1. ATR Position Sizing OOS

### Train-best → Test 결과

| 종목 | RSI baseline | ATR (train_best) | vs RSI | MaxDD | B/S | risk | atr_m | 판정 |
|------|-------------|-------------------|--------|-------|-----|------|-------|------|
| SOXL | +463.1% | +463.1% | +0.0% | -34.2% | 7B/6S | 1.0 | 1.0 | 동일 |
| TQQQ | +135.9% | +135.9% | +0.0% | -74.7% | 19B/18S | 1.0 | 1.0 | 동일 |
| SPXL | +294.9% | +294.9% | +0.0% | -70.5% | 12B/11S | 1.0 | 1.0 | 동일 |
| TNA | +75.5% | +75.5% | +0.0% | -84.8% | 14B/13S | 1.0 | 1.0 | 동일 |
| **QLD** | **+100.9%** | **+127.5%** | **+26.6%** | **-41.8%** | **10B/9S** | **0.05** | **1.5** | **PASS** |
| UWM | +160.7% | +65.4% | -95.3% | -45.4% | 13B/12S | 0.05 | 2.0 | FAIL |
| QQQ | +67.9% | +67.9% | +0.0% | -29.6% | 5B/4S | 1.0 | 1.0 | 동일 |

### 핵심 발견

1. **대부분 종목에서 all-in이 최적**: train에서 risk=1.0/atr_mult=1.0이 best → ATR sizing 자체가 수익률 향상에 기여하지 않음
2. **QLD만 OOS 통과**: risk=0.05, atr_mult=1.5 → 수익률 +26.6%p 개선, MaxDD -14%p 개선 (55.8% → 41.8%)
3. **TQQQ MaxDD 개선 가능성**: risk=0.05, atr_mult=2.0 → 수익률 -14.5%p 손실이지만 MaxDD 74.7% → 35.6%로 절반 감소
4. **ATR sizing의 진짜 가치는 리스크 관리**: 수익률은 떨어지지만 MaxDD를 크게 줄일 수 있음

### MaxDD vs 수익률 트레이드오프 (TQQQ 예시)

| risk | atr_m | Return% | vs RSI | MaxDD% | DD 개선 |
|------|-------|---------|--------|--------|---------|
| 1.0 | 1.0 | +135.9% | 0.0% | -74.7% | 기준 |
| 0.1 | 2.0 | +194.9% | +59.0% | -58.4% | +16.3%p |
| 0.05 | 1.5 | +174.5% | +38.6% | -46.6% | +28.1%p |
| 0.05 | 2.0 | +121.4% | -14.5% | -35.6% | **+39.1%p** |
| 0.02 | 1.5 | +55.4% | -80.5% | -19.5% | +55.2%p |

---

## 2. VIX Term Structure OOS

### Train-best → Test 결과

| 종목 | RSI test | train→test | vs RSI | 판정 | test actual best | params |
|------|----------|-----------|--------|------|-----------------|--------|
| SOXL | +463.1% | +0.0% | -463.1% | **FAIL** (0거래) | +457.5% | force r>1.15 (9B/8S) |
| TQQQ | +135.9% | +104.4% | -31.5% | **FAIL** | +143.0% | adjust r>1.15 (17B/16S) |
| SPXL | +294.9% | +309.0% | +14.1% | **PASS** (소폭) | +955.0% | block r>1.05 (12B/11S) |
| TNA | +75.5% | +49.0% | -26.5% | **FAIL** | +831.9% | block+force r>1.1 (19B/18S) |

### 핵심 발견

1. **과적합 전형적 패턴**: train best ≠ test best. train에서 "adjust" 모드가 best였으나 test에서는 "block"/"block+force"가 우세
2. **SOXL adjust r>1.2**: train에서 +21,494%였으나 test에서 0거래 (adjust 모드가 backwardation 잦은 2020년대에 매수 조건을 너무 강화)
3. **SPXL block r>1.05**: test에서 +955% (RSI +295% 대비 3.2배) — backwardation 시 매수 차단이 2020년 코로나 폭락을 완벽 회피
4. **TNA block+force r>1.1**: test에서 +832% (RSI +76% 대비 11배) — 같은 원리
5. **문제**: 이 최적 파라미터를 사전에 알 수 없음 → 자동 시그널로는 불안정

### In-sample vs OOS 비교 (VIX term beat RSI 비율)

| 종목 | In-sample beat RSI | OOS train_best | 갭 |
|------|-------------------|----------------|-----|
| SOXL | 8/25 (32%) | FAIL | 과적합 |
| TQQQ | 7/25 (28%) | FAIL | 과적합 |
| SPXL | 7/25 (28%) | PASS (+14%) | 소폭 유효 |
| TNA | 7/25 (28%) | FAIL | 과적합 |

---

## 3. 종합 결론

### 적용 가능한 것

| 전략 | 자동 시그널 | 정보 표시 | 포지션 조언 | 판정 |
|------|-----------|----------|------------|------|
| ATR sizing (수익 최대화) | X | - | - | all-in이 최적 |
| ATR sizing (리스크 관리) | X | O | **O** | MaxDD 감소 효과 |
| VIX term (자동 매매) | **X** | - | - | 과적합 |
| VIX term (정보 표시) | - | **O** | **O** | 조언용 유효 |

### alert.py 반영 내용

1. **VIX Term Structure** → 매크로 섹션에 contango/backwardation 상태 표시
   - 콘탱고: 정상 시장 (🟢)
   - 백워데이션: 공포 시장 (🔴) + "포지션 축소 or 신규 진입 주의" 조언
2. **ATR 변동성** → 매수/재매수 시그널에 포지션 사이징 조언 첨부
   - ATR > 평균의 1.5배: "50% 포지션 권장"
   - ATR > 평균의 1.2배: "70% 포지션 권장"
   - 그 외: "풀 포지션 가능"
3. **강제 시그널 변경 없음** → OOS 검증 미통과 전략은 자동 적용하지 않음

### 다음 실험 후보

1. **Walk-forward 최적화**: 고정 분할 대신 rolling window로 파라미터 재최적화
2. **VIX term + RSI 임계값 결합**: VIX backwardation 시 buy_rsi를 5 낮추는 식 (단, OOS 필수)
3. **ATR 기반 stop-loss**: 포지션 사이징이 아닌 ATR x 2 trailing stop
4. **레짐별 파라미터 스위칭**: contango/backwardation 레짐마다 다른 RSI 파라미터 세트
