# `--run-all` 전 종목 종합 분석 + 상위 결과 HTML 보고서

## Context
13종목 전체 그리드서치 + 프리셋 시나리오 + 단일 vs 혼합.
전부 돌린 후 가장 좋은 결과들만 뽑아서 HTML 보고서(차트 포함).

## Phase 1: 매매 이유 인프라 (1 step)
- strategies/base.py: generate_signals → (signals, reasons) 튜플
- bb_rsi_ema.py: reason 생성
- portfolio.py: buy/sell에 reason
- engine.py: trade_log에 reason

## Phase 2: full_analysis + runner (1 step)
- full_analysis.py: 종목별 그리드서치 + 프리셋 + 단일vs혼합 (기간별)
- top_picks: Sharpe 상위 N개 선별
- runner.py: --run-all, --fast-grid, --periods, --top-picks

## Phase 3: HTML 차트 보고서 (1 step)
- charts.py: Plotly 차트 (매매 마커 + hover 이유 + rangeselector)
- report.py: top picks만 차트 포함 HTML 생성

## Phase 4: 테스트 (1 step)
- test_full_analysis.py (8 TC), test_charts.py (4 TC)
