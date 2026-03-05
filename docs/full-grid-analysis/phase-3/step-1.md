# Phase 3 - Step 1: Plotly 차트 함수

## 목표
- requirements.txt에 plotly 추가
- report_html.py (신규): 개별 차트 생성 함수들

## 변경 파일
- `requirements.txt` — `plotly>=5.18` 추가
- `backtest/report_html.py` — 신규 생성

## 구현 상세

### report_html.py
- `create_symbol_chart(df, trades, equity_curve, symbol, bh_curve=None)`: 가격 + BUY/SELL 마커 + hover reason + B&H 오버레이
- `create_preset_comparison_chart(preset_results)`: 프리셋별 성과 bar chart
- `create_period_comparison_chart(period_results, symbol)`: 기간별 성과 bar chart

## 완료 조건
- ✅ 각 차트 함수가 plotly Figure 객체 반환
- ✅ hover 정보에 reason 포함
- ✅ 8/8 tests passed

## TC

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
