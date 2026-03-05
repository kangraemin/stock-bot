# 전 종목 Grid Search + HTML 보고서

## Context
13종목 전체 grid search(49,152 파라미터 조합) → 종목별 Top 5 → Plotly 인터랙티브 HTML 보고서.

## Grid: 49,152 조합 × 2수수료 × 2시간대 × 3기간 × 13종목 = ~7.7M회

**파라미터:** bb_window[4] × bb_std[4] × rsi_window[3] × ema_window[4] × rsi_buy[4] × rsi_sell[4] × ema_filter[2] × macd_filter[2] × volume_filter[2] × adx_filter[2]

## Phase 1: 전략 확장 + reason 인프라
- bb_rsi_ema.py: RSI 임계값 파라미터화 + EMA/MACD/Volume/ADX 필터 on/off + reason
- base.py: generate_signals_with_reasons()
- portfolio.py/engine.py: reason 전달 경로

## Phase 2: 전 종목 Grid Search + 병렬화
- grid_search.py: run_full_grid_search() + ProcessPoolExecutor
- data_loader.py: resample_to_weekly()

## Phase 3: Plotly HTML 보고서
- report_html.py (신규): 차트 + 마커 + hover reason + B&H + 프리셋 비교

## Phase 4: CLI 통합
- runner.py: --full-report
