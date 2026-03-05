# Phase 4 - Step 1: CLI 통합

## 목표
- runner.py: --full-report 플래그 추가
- runner.py: run_full_analysis() 함수 구현
  - grid search 실행 → HTML 보고서 생성 파이프라인

## 변경 파일
- `src/runner.py`

## 테스트 항목 (7 TCs, `tests/test_runner.py` TC-9~15)

| TC | 설명 |
|----|------|
| TC-9 | `--full-report` CLI 플래그 파싱 |
| TC-10 | `--periods` 파라미터 기본값 ("1y,3y,5y") |
| TC-11 | `--timeframes` 파라미터 기본값 ("daily,weekly") |
| TC-12 | `--output` 파라미터 기본값 ("full_report.html") |
| TC-13 | `--top-n` 파라미터 기본값 (5) |
| TC-14 | `--n-jobs` 파라미터 파싱 |
| TC-15 | `run_full_analysis` 함수 존재 및 callable |

## 완료 조건
- python -m src.runner --full-report 실행 가능
- grid search → 보고서 생성 파이프라인 정상 동작
