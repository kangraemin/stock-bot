# Stock-Bot Project Rules

## 결과 보고 규칙

- 백테스트 결과를 사용자에게 말할 때 **거래 횟수(B/S)를 반드시 포함**한다.
- 수익률, MaxDD, 거래횟수는 항상 세트로 보고한다.

## 실험 → 결과 저장 패턴

백테스트나 분석 실험을 실행한 후 반드시 결과를 저장한다.

### 파일 구조
- 백테스트 코드: 프로젝트 루트 (`*_backtest.py`)
- 결과 CSV: `results/`
- 분석 문서: `analysis/backtest/YYYY-MM-DD-<주제>.md`
- 인덱스: `analysis/INDEX.md`

### 분석 문서 포맷
```markdown
# 제목

- 날짜: YYYY-MM-DD
- 백테스트 코드: `파일명.py`
- 결과 CSV: `results/파일명.csv`

## 개요
한 줄 설명

## 파라미터 / 그리드
테스트한 파라미터 범위

## 결과 요약
핵심 수치 테이블

## 핵심 인사이트
번호 매긴 발견사항 (데이터 근거 포함)

## 한계점
알려진 제약

## 후속 방향
다음에 시도할 것
```

### 인덱스 업데이트
`analysis/INDEX.md` 테이블에 한 줄 추가. 형식:
```
| 날짜 | 카테고리 | 제목 | 파일링크 | 핵심 결과 한 줄 |
```

## 데이터

- 주가 데이터: `data/*.parquet` (yfinance, `download.py`로 다운로드)
- 매크로 데이터: `data/` (HG=F, CL=F, ^VIX, GC=F, ^TNX, DX-Y.NYB)

## 알림봇

- `alert.py`: 멀티 종목 텔레그램 알림 (cron 매일 KST 06:00)
- 배포: Oracle Cloud (ubuntu@158.179.166.232), ~/stock-bot/
- 상태 파일: `.states/*.json`
