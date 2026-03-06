# alert.py 8~9월 계절적 약세 경고 추가

## Context
8~9월 회피 전략이 롤링 OOS 24/24 통과 (과적합 아님 확인). 매수를 차단하지 않고, 경고 문구만 추가.

## 변경 파일
- `alert.py` (1개)

## 변경 내용

### `_what_to_do()` 함수
BUY/REBUY 시그널 반환 문자열에 8~9월이면 경고 문구 덧붙이기:

- `import datetime` 추가
- 함수 시작부에 `month = datetime.date.today().month`
- `seasonal_warn = " ⚠️ 계절적 약세 구간 (8~9월)" if month in (8, 9) else ""`
- BUY/REBUY 반환값 4곳에 `{seasonal_warn}` 추가

## 개발 Phase

- Phase 1, Step 1: `_what_to_do()`에 월 체크 + 경고 문구 추가

## 검증
- `python -c "import alert"` 에러 없음 확인
