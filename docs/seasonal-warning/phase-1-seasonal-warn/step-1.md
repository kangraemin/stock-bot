# Phase 1 Step 1: _what_to_do()에 8~9월 경고 추가

## 테스트 기준

| TC | 설명 | 결과 |
|----|------|------|
| TC-1 | `import datetime` 추가됨 | ✅ |
| TC-2 | `_what_to_do()`에서 `month = datetime.date.today().month` 체크 | ✅ |
| TC-3 | BUY 반환값에 8~9월이면 경고 문구 포함 | ✅ |
| TC-4 | REBUY 반환값에 8~9월이면 경고 문구 포함 | ✅ |
| TC-5 | `python -c "import alert"` 에러 없음 | ✅ |
