# Phase 4 Step 2: grid_search.py hourly 구현

## 변경
- run_grid_search: periods_per_year 파라미터 → compute_metrics_fast 전달
- _run_symbol: hourly_df 파라미터, tf=="hourly" 분기, periods_per_year 전달
- run_full_grid_search: hourly_data 파라미터 → _run_symbol에 전달
