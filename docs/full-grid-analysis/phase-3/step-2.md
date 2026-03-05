# Phase 3 - Step 2: HTML 보고서 조립

## 목표
- report_html.py: generate_full_html_report() 구현
  - 종목별 섹션으로 차트 조립
  - 단일 HTML 파일 출력 (인터랙티브)

## 변경 파일
- `src/report_html.py`

## 테스트 항목 (7 TCs, `tests/test_report_html.py` TC-9~15)

| TC | 설명 |
|----|------|
| TC-9 | `create_grid_results_table()` → HTML string 반환 |
| TC-10 | grid results table에 파라미터 + 메트릭스 포함 |
| TC-11 | `generate_full_html_report()` 파일 생성 + 크기 > 0 |
| TC-12 | HTML에 plotly 스크립트 포함 |
| TC-13 | HTML에 종목별 앵커 네비게이션 |
| TC-14 | HTML에 종목별 차트 섹션 포함 |
| TC-15 | `generate_full_html_report()` 경로 string 반환 |

## 완료 조건
- generate_full_html_report()가 HTML 파일 경로 반환
- 13종목 전체 포함된 단일 HTML
- 브라우저에서 인터랙티브 동작
