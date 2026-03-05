# Phase 3 - Step 3: Phase 3 테스트

## 목표
- report_html.py 단위 테스트 작성

## 변경 파일
- `tests/test_report_html.py` (신규)

## 테스트 항목 (TC 요약)

### Step 1 — Plotly 차트 함수 (8 TCs, `tests/test_report_html.py`)
| TC | 설명 | 상태 |
|----|------|------|
| TC-1 | `plotly` in requirements.txt | ✅ pass |
| TC-2 | `backtest.report_html` 모듈 import 가능 | ✅ pass |
| TC-3 | `create_symbol_chart()` → `go.Figure` 반환 | ✅ pass |
| TC-4 | BUY/SELL 마커 trace 포함 | ✅ pass |
| TC-5 | hover customdata에 reason 포함 | ✅ pass |
| TC-6 | `create_preset_comparison_chart()` → `go.Figure` 반환 | ✅ pass |
| TC-7 | `create_period_comparison_chart()` → `go.Figure` 반환 | ✅ pass |
| TC-8 | B&H curve 오버레이 (bh_curve 파라미터) | ✅ pass |

### Step 2 — HTML 보고서 조립 (7 TCs, `tests/test_report_html.py`)
| TC | 설명 | 상태 |
|----|------|------|
| TC-9 | `create_grid_results_table()` → HTML string 반환 | ✅ pass |
| TC-10 | grid results table에 파라미터 + 메트릭스 포함 | ✅ pass |
| TC-11 | `generate_full_html_report()` 파일 생성 + 크기 > 0 | ✅ pass |
| TC-12 | HTML에 plotly 스크립트 포함 | ✅ pass |
| TC-13 | HTML에 종목별 앵커 네비게이션 | ✅ pass |
| TC-14 | HTML에 종목별 차트 섹션 포함 | ✅ pass |
| TC-15 | `generate_full_html_report()` 경로 string 반환 | ✅ pass |

### 검증 기준
- 전체 회귀 테스트 170/170 통과 (Phase 1 + Phase 2 + Phase 3 포함)
