# Phase 3 - Step 1: Plotly 차트 함수

## 목표
- requirements.txt에 plotly 추가
- report_html.py (신규): 개별 차트 생성 함수들
  - 주가 + 매매 마커 (hover에 reason 표시)
  - B&H 대비 수익률 비교
  - 파라미터 히트맵
  - 프리셋 비교 바 차트

## 변경 파일
- `requirements.txt`
- `src/report_html.py` (신규)

## 테스트 항목 (8 TCs, `tests/test_report_html.py`)

| TC | 설명 |
|----|------|
| TC-1 | `plotly` in requirements.txt |
| TC-2 | `backtest.report_html` 모듈 import 가능 |
| TC-3 | `create_symbol_chart()` → `go.Figure` 반환 |
| TC-4 | BUY/SELL 마커 trace 포함 |
| TC-5 | hover customdata에 reason 포함 |
| TC-6 | `create_preset_comparison_chart()` → `go.Figure` 반환 |
| TC-7 | `create_period_comparison_chart()` → `go.Figure` 반환 |
| TC-8 | B&H curve 오버레이 (bh_curve 파라미터) |

## 완료 조건
- 각 차트 함수가 plotly Figure 객체 반환
- hover 정보에 reason 포함
