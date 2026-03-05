# stock-bot 백테스트 엔진 + 데이터 다운로드 (v3)

## Context
미국 주식 자동매매 봇의 백테스트 시스템. coinbot 구조 참고하되 주요 개선:
- 3x 레버리지 ETF 포함 (TQQQ, SPXL 등)
- 멀티 포지션 포트폴리오 (여러 종목 동시 보유)
- 포트폴리오 리밸런싱
- 파라미터 그리드 서치 (그리디 최적화)
- Buy & Hold 대비 성과 비교 필수
- 수수료 왕복 0.5% 반드시 적용
- **거래 횟수 지표 필수**
- **단일 종목 vs 혼합 포트폴리오 비교**
- **성장주+안전주 프리셋 포트폴리오 비교**

## 프로젝트 구조

```
stock-bot/
  config.py                  # 전역 설정
  download.py                # yfinance 다운로더 CLI
  data/                      # Parquet (gitignored)
  backtest/
    __init__.py
    engine.py                # 단일 + 포트폴리오 백테스트 엔진
    portfolio.py             # Portfolio 클래스 (멀티 포지션)
    rebalancer.py            # 리밸런싱 로직
    grid_search.py           # 파라미터 그리드 서치
    buyhold.py               # Buy & Hold 비교
    comparisons.py           # 포트폴리오 프리셋 비교 (단일 vs 혼합, 성장 vs 안전)
    data_loader.py           # Parquet 로드
    metrics.py               # 성과 지표
    report.py                # 터미널 + HTML 리포트
    runner.py                # CLI 진입점
    strategies/
      __init__.py            # 전략 레지스트리
      base.py                # Strategy ABC
      bb_rsi_ema.py          # BB+RSI+EMA 평균회귀
  tests/
    test_engine.py
    test_portfolio.py
    test_grid_search.py
    test_buyhold.py
    test_comparisons.py
    test_strategies.py
    test_data_loader.py
    test_metrics.py
  requirements.txt
  .gitignore
```

## 개발 Phase

### Phase 1: 기반 설정
- `config.py`:
  - SYMBOLS_BASE: SPY, QQQ, AAPL, MSFT, GOOGL, AMZN, NVDA, TSLA
  - SYMBOLS_3X: TQQQ, SPXL, SOXL, UPRO, TECL
  - LEVERAGE_MAP: 3x ETF -> 기초자산 매핑
  - FeeModel: STANDARD=0.25%, EVENT=0.09%
  - 슬리피지 0.1%, 자본 $2,000
  - 포트폴리오 프리셋 정의:
    - PRESET_GROWTH: TQQQ, TECL, SOXL, NVDA, TSLA (성장주)
    - PRESET_SAFE: SPY, MSFT, GOOGL, AAPL (안전주)
    - PRESET_MIXED: TQQQ 30%, SPXL 20%, SPY 20%, MSFT 15%, AAPL 15%
    - PRESET_ALL_3X: TQQQ, SPXL, SOXL, UPRO, TECL 균등
- `download.py`: 13종목 + SOXX, XLK(3x 기초자산) 다운로드, Parquet 저장, 캐시
- `requirements.txt`: yfinance, pandas, numpy, ta, matplotlib, pyarrow
- `.gitignore`: data/, __pycache__, .venv, backtest/output/

### Phase 2: 데이터 + 전략 인터페이스
- `backtest/data_loader.py`: Parquet 로드, 날짜 필터, load_multi(symbols) -> dict
- `backtest/strategies/base.py`: Strategy ABC (generate_signals -> Signal, params property)
- `backtest/strategies/bb_rsi_ema.py`: BB+RSI+EMA -> 롱, 파라미터 생성자 주입
- `backtest/strategies/__init__.py`: STRATEGIES 레지스트리

### Phase 3: 포트폴리오 + 엔진
- `backtest/portfolio.py`: Portfolio 클래스
  - buy/sell 시 수수료 강제 차감
  - get_total_equity, get_weights, update_equity, trade_log, **trade_count**
- `backtest/engine.py`:
  - run_backtest() 단일 종목용
  - run_portfolio_backtest() 멀티 포지션
  - 결과에 **total_trades(거래 횟수)** 항상 포함
- `backtest/rebalancer.py`: 리밸런싱 (equal/custom/risk_parity, 임계값 2%p)

### Phase 4: B&H 비교 + 그리드 서치 + 프리셋 비교
- `backtest/buyhold.py`:
  - compute_buyhold(), compare_vs_buyhold(), compare_by_period()
- `backtest/grid_search.py`:
  - ~9700 조합 탐색, 결과에 **total_trades + vs_buyhold_excess** 필수
- `backtest/comparisons.py` (NEW):
  - PRESETS dict (config.py에서 가져옴)
  - run_single_vs_portfolio(): 각 종목 단독 vs 혼합 포트폴리오 성과 비교
  - run_preset_comparison(): 성장주/안전주/혼합/3x전용 프리셋끼리 비교
  - 비교 지표: 수익률, MDD, Sharpe, **거래 횟수**, B&H 대비 초과수익
  - 출력: 프리셋별 비교 테이블
- `backtest/metrics.py`:
  - 기존 + calmar_ratio, information_ratio, turnover, avg_holding_days, **total_trades**

### Phase 5: 리포트 + CLI
- `backtest/report.py`:
  - print_summary() (거래 횟수 포함)
  - print_vs_buyhold()
  - print_preset_comparison() — 프리셋 비교 테이블
  - print_grid_results(top_n)
  - generate_html_report()
- `backtest/runner.py` CLI:
  - --symbols, --portfolio, --weights, --rebalance, --fee-rate
  - --grid-search, --capital, --report html
  - --compare-buyhold (기본 ON)
  - --compare-presets — 프리셋 포트폴리오 비교 모드
  - --single-vs-mixed — 단일 종목 vs 혼합 비교 모드

### Phase 6: 테스트
- test_engine.py, test_portfolio.py, test_grid_search.py, test_buyhold.py
- test_comparisons.py (프리셋 비교 검증)
- test_strategies.py, test_data_loader.py, test_metrics.py

## 핵심 설계 결정

| 항목 | 결정 | 이유 |
|------|------|------|
| 3x ETF 처리 | engine에서 추가 레버리지 없음 | ETF 자체가 3x |
| 수수료 강제 | Portfolio.buy/sell 내부에서 차감 | 누락 원천 차단 |
| 거래 횟수 | 모든 결과에 total_trades 필수 | 수수료 임팩트 판단 기준 |
| 프리셋 비교 | 성장/안전/혼합/3x 프리셋 | 포트폴리오 구성 효과 검증 |
| 단일 vs 혼합 | 종목별 단독 vs 조합 비교 | 분산 투자 효과 확인 |
| 리밸런싱 임계값 | 2%p 이상 차이 시만 | 수수료 낭비 방지 |
| B&H 비교 | 기본 ON | 벤치마크 필수 |
| 배당 | auto_adjust=True | 수정주가로 자동 반영 |

## 검증 방법
1. `python download.py` -> data/에 15종목 Parquet 생성 확인
2. `python -m backtest.runner --symbol SPY` -> 단일 종목 + B&H + 거래횟수 출력
3. `python -m backtest.runner --symbols TQQQ SPXL SOXL --portfolio --rebalance monthly` -> 포트폴리오
4. `python -m backtest.runner --symbols TQQQ --grid-search` -> 그리드 서치 (거래횟수 포함)
5. `python -m backtest.runner --compare-presets` -> 성장/안전/혼합 프리셋 비교 테이블
6. `python -m backtest.runner --single-vs-mixed` -> 단일 종목 vs 혼합 비교
7. `python -m pytest tests/` -> 전체 테스트 통과
8. 수수료 0% vs 0.25% 차이 확인
