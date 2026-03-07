# alert.py 포맷 통일: 공통 포맷팅 함수 추출

## 변경 사항

### 1. `alert.py` — 공통 포맷팅 함수 추출
- `format_full_report()`: 전 종목 리포트 문자열 반환
- `format_single_report()`: 단일 종목 상세 문자열 반환
- `main()`은 `format_full_report()` 호출 후 `send_telegram()`

### 2. `bot_listener.py` — alert 공통 함수 사용
- `build_status()`: 자체 포맷팅 제거, `alert.format_full_report()` / `alert.format_single_report()` 호출

## 검증
- pytest 전체 통과
- import 확인
