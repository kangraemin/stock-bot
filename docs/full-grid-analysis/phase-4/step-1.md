# Phase 4 - Step 1: CLI 통합

## 목표
- runner.py: --full-report 플래그 + 관련 CLI 옵션 추가
- runner.py: run_full_analysis() 함수 구현

## 변경 파일
- `backtest/runner.py` — CLI 옵션 6개 추가, run_full_analysis() 구현

## 구현 상세

### CLI 옵션 추가
- `--full-report`: 전체 분석 파이프라인 실행
- `--periods`: 기본 "1y,3y,5y"
- `--timeframes`: 기본 "daily,weekly"
- `--output`: 기본 "full_report.html"
- `--top-n`: 기본 5
- `--n-jobs`: 기본 None

### run_full_analysis(args)
- SYMBOLS_BASE + SYMBOLS_3X 전체 로드
- run_full_grid_search() 호출 (periods, timeframes, fee_rates, n_jobs)
- symbol_data 구성 후 generate_full_html_report() 호출
- 파일 경로 출력

## 완료 조건
- ✅ CLI 플래그 및 파라미터 파싱 정상
- ✅ run_full_analysis callable
- ✅ 15/15 tests passed

## TC

| TC | 설명 | 상태 |
|----|------|------|
| TC-9 | `--full-report` CLI 플래그 파싱 | ✅ pass |
| TC-10 | `--periods` 파라미터 기본값 ("1y,3y,5y") | ✅ pass |
| TC-11 | `--timeframes` 파라미터 기본값 ("daily,weekly") | ✅ pass |
| TC-12 | `--output` 파라미터 기본값 ("full_report.html") | ✅ pass |
| TC-13 | `--top-n` 파라미터 기본값 (5) | ✅ pass |
| TC-14 | `--n-jobs` 파라미터 파싱 | ✅ pass |
| TC-15 | `run_full_analysis` 함수 존재 및 callable | ✅ pass |
