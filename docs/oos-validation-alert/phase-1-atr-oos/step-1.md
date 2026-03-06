# Step 1: exp2_atr_sizing_oos.py 생성

## 테스트 케이스

| # | 테스트 | 기대 결과 | 실제 결과 |
|---|--------|-----------|-----------|
| 1 | `python exp2_atr_sizing_oos.py` 실행 시 에러 없이 완료 | exit 0 | ✅ |
| 2 | 각 종목별 TRAIN/TEST 결과 출력 | B&H, RSI baseline, ATR best 모두 출력 | ✅ |
| 3 | 거래 횟수(B/S) 포함 | 모든 결과에 nB/nS 표시 | ✅ |
| 4 | results/exp2_atr_sizing_oos.csv 생성 | CSV 파일 존재 | ✅ |

## 구현 내용

- `exp2_atr_sizing_oos.py` 생성: train(<2020)/test(>=2020) 분할, 7종목 x 28콤보
- `exp5_vix_term_oos.py` 실행 완료
- OOS 결과: ATR sizing은 대부분 all-in이 최선 (QLD만 OOS 통과), VIX term은 train_best 대부분 FAIL
- alert.py에 VIX term 정보 표시 + ATR 변동성 기반 포지션 조언 추가
