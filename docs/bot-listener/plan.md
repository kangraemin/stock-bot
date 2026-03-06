# 텔레그램 봇 리스너 (/status 명령어)

## Context
현재 alert.py는 cron으로 하루 1회 일방향 발송만 한다.
/status 명령어로 실시간 조회 기능을 추가한다.

## Phase 1: bot_listener.py 생성
- alert.py 함수 import 재사용
- long polling + /status, /help 명령어

## Phase 2: systemd 서비스 파일
## Phase 3: 테스트
