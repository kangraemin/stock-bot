# Step 1: alert.py 포지션 조언 추가

## 테스트 케이스

| # | 테스트 | 기대 결과 | 실제 결과 |
|---|--------|-----------|-----------|
| 1 | alert.py 구문 검사 통과 | ast.parse OK | ✅ |
| 2 | get_vix_term() 함수 존재 | 함수 정의 확인 | ✅ |
| 3 | get_atr_ratio() 함수 존재 | 함수 정의 확인 | ✅ |
| 4 | _position_advice() 함수 존재 | 함수 정의 확인 | ✅ |
| 5 | 매크로 섹션에 VIX term 표시 | 코드 확인 | ✅ |
| 6 | BUY/REBUY 시그널에 포지션 조언 포함 | 코드 확인 | ✅ |
| 7 | 용어 설명에 VIX Term, ATR 추가 | 코드 확인 | ✅ |
| 8 | pytest 통과 | 기존 테스트 영향 없음 | ✅ (183 passed, 1 known fail) |

## 구현 내용

- `get_vix_term()`: VIX/VIX3M ratio → contango/neutral/backwardation
- `get_atr_ratio()`: 현재 ATR vs 60일 평균 ATR → 변동성 수준
- `_position_advice()`: ATR ratio + VIX status → 포지션 사이징 조언
- 매크로 섹션에 VIX term 상태 표시 (콘탱고/백워데이션)
- BUY/REBUY 시 포지션 조언 메시지 추가
- DCA 구간에서 변동성 높으면 소량 추천 표시
