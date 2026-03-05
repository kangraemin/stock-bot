# Phase 5 Step 1: report.py

## 목표
터미널 + HTML 리포트

## 구현 대상
- `backtest/report.py`: print_summary(), print_vs_buyhold(), print_preset_comparison(), print_grid_results(), generate_html_report()

## TC

| TC | 설명 | 검증 |
|----|------|------|
| TC-1 | print_summary 출력 | 에러 없이 실행, 거래 횟수 포함 |
| TC-2 | print_vs_buyhold 출력 | excess_return 포함 |
| TC-3 | print_preset_comparison 출력 | 프리셋별 비교 테이블 |
| TC-4 | print_grid_results 출력 | top_n 결과 출력 |
| TC-5 | generate_html_report | HTML 문자열 반환 |
| TC-6 | HTML에 거래 횟수 포함 | total_trades 텍스트 포함 |
