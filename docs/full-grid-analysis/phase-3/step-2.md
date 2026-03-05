# Phase 3 - Step 2: HTML 보고서 조립

## 목표
- report_html.py: generate_full_html_report() + create_grid_results_table() 구현

## 변경 파일
- `backtest/report_html.py` — create_grid_results_table(), generate_full_html_report() 추가

## 구현 상세

### create_grid_results_table(grid_results) -> str
- grid_results 리스트를 HTML 테이블로 변환
- params, total_return, sharpe_ratio, max_drawdown, total_trades 컬럼

### generate_full_html_report(symbol_data, grid_results, preset_results, output_path) -> str
- Plotly CDN 스크립트 포함
- 종목별 앵커 네비게이션 (id="{symbol}", href="#{symbol}")
- 종목별 섹션: create_symbol_chart → pio.to_html(include_plotlyjs=False)
- Grid results 테이블, Preset comparison 차트 (optional)
- 파일 경로 string 반환

## 완료 조건
- ✅ generate_full_html_report()가 HTML 파일 경로 반환
- ✅ 종목별 앵커 네비게이션 + 차트 섹션
- ✅ 15/15 tests passed

## TC

| TC | 설명 | 상태 |
|----|------|------|
| TC-9 | `create_grid_results_table()` → HTML string 반환 | ✅ pass |
| TC-10 | grid results table에 파라미터 + 메트릭스 포함 | ✅ pass |
| TC-11 | `generate_full_html_report()` 파일 생성 + 크기 > 0 | ✅ pass |
| TC-12 | HTML에 plotly 스크립트 포함 | ✅ pass |
| TC-13 | HTML에 종목별 앵커 네비게이션 | ✅ pass |
| TC-14 | HTML에 종목별 차트 섹션 포함 | ✅ pass |
| TC-15 | `generate_full_html_report()` 경로 string 반환 | ✅ pass |
