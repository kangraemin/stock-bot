# Verification Round 2

| # | 항목 | 결과 |
|---|------|------|
| 1 | exp2_atr_sizing_oos.py train/test 분할 + CSV 데이터 존재 | PASS |
| 2 | get_vix_term(): VIX/VIX3M ratio, contango/backwardation 판별 | PASS |
| 3 | get_atr_ratio(): TR/ATR 계산, current/avg ratio | PASS |
| 4 | _position_advice(): ATR>1.5→50%, >1.2→70%, VIX backwardation 경고 | PASS |
| 5 | 매크로 섹션: copper + vix term 독립 표시 | PASS |
| 6 | main()→_position_advice() vix_status 전달 흐름 | PASS |
| 7 | 구문 검사 + pytest (95 passed, 1 known fail) | PASS |

**최종: PASS**
