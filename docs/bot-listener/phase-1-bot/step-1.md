# Step 1: bot_listener.py 생성

## TC

| # | 항목 | 예상 | 실제 |
|---|------|------|------|
| TC-1 | bot_listener.py 구문 검사 통과 | PASS | ✅ |
| TC-2 | build_status() 전종목 → 모든 SYMBOLS 포함 | PASS | ✅ |
| TC-3 | build_status("SOXL") → SOXL 상세 | PASS | ✅ |
| TC-4 | build_status("INVALID") → 에러 메시지 | PASS | ✅ |
| TC-5 | build_help() → /status, /help 안내 | PASS | ✅ |
| TC-6 | handle_message /status → send_reply 호출 | PASS | ✅ |
| TC-7 | handle_message unknown → send_reply 미호출 | PASS | ✅ |

[STEP:1:테스트통과]
