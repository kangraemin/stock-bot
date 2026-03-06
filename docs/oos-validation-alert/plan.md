# OOS Validation + Alert Position Advice

## Context
VIX Term Structure(exp5)와 ATR Position Sizing(exp2) 백테스트가 in-sample에서 유망한 결과를 보였다.
OOS 검증(train < 2020, test >= 2020)을 통과하면 alert.py에 포지션 사이징/스위칭 조언을 추가한다.

## 개발 Phase

### Phase 1: exp2_atr_sizing_oos.py 생성
- exp5_vix_term_oos.py 패턴을 따라 ATR sizing OOS 검증 스크립트 작성
- 파라미터: risk_pct [0.01, 0.02, 0.05, 0.10, 0.20, 0.50, 1.0], atr_mult [1.0, 1.5, 2.0, 3.0]
- 7종목(SOXL, TQQQ, SPXL, TNA, QLD, UWM, QQQ)
- train best → test 적용, 전체 콤보 test 결과 출력
- 결과 CSV: results/exp2_atr_sizing_oos.csv

**파일**: `exp2_atr_sizing_oos.py` (신규)

### Phase 2: OOS 백테스트 실행
- `.venv/bin/python exp5_vix_term_oos.py` 실행
- `.venv/bin/python exp2_atr_sizing_oos.py` 실행
- 결과 분석: train best가 test에서도 RSI baseline 대비 개선되는지 확인

### Phase 3: alert.py에 포지션 조언 추가
OOS 통과한 전략만 반영. 예상 반영 항목:

1. **VIX Term Structure 조언** (OOS 통과 시):
   - `get_vix_term()` 함수 추가: VIX/VIX3M ratio 계산
   - contango/backwardation 상태를 메시지에 표시
   - backwardation 시 "포지션 축소 권장" / contango 시 "정상 진입 가능" 조언

2. **ATR 포지션 사이징 조언** (OOS 통과 시):
   - `get_atr_advice()` 함수 추가: 현재 ATR 대비 평균 ATR 비교
   - 변동성 높을 때 "포지션 50% 축소 권장", 낮을 때 "풀 포지션 가능" 등

3. **메시지 포맷 변경**:
   - 기존 매크로 섹션 확장: 구리 + VIX term + 변동성
   - `_what_to_do()` 메시지에 포지션 사이징 힌트 추가
   - 용어 설명 footer에 VIX term, ATR 추가

**파일**: `alert.py` (수정)

## 주요 파일
- `exp5_vix_term_oos.py` (기존, 실행만)
- `exp2_atr_sizing_oos.py` (신규 생성)
- `exp2_atr_sizing_backtest.py` (참조: ATR sizing 로직)
- `alert.py` (수정: 조언 추가)

## 검증
1. exp2_atr_sizing_oos.py 실행 → 에러 없이 완료
2. exp5_vix_term_oos.py 실행 → 에러 없이 완료
3. OOS 결과에서 train_best가 test RSI baseline 대비 개선 확인
4. alert.py 수정 후 `python alert.py` dry-run 또는 구문 검사
5. 기존 pytest 테스트 통과 확인
