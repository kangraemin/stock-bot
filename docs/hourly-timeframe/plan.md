# 시간봉(1h) 타임프레임 지원 추가

## Context

현재 백테스트는 일봉/주봉만 지원. 일봉 그리드 서치 결과에서 거래 횟수가 2~3회로 통계적 유의성이 낮음. 시간봉(1h)을 추가하면 데이터 포인트 ~19배 증가, 거래 횟수 확보로 신뢰도 향상. yfinance 무료 API로 최대 730일 시간봉 데이터 사용.

## 설계 결정

- **방식 C**: `hourly_data` 별도 파라미터 — 기존 data dict 구조 변경 없이 최소 수정
- **파일명 규칙**: `SPY.parquet` (일봉), `SPY_1h.parquet` (시간봉)
- **Sharpe 연환산**: `periods_per_year` 파라미터화 (일봉=252, 시간봉=1638)
- **하위 호환**: 모든 변경은 기본값으로 기존 동작 유지

---

## Phase 1: download.py — interval 파라미터

### Step 1: 테스트 정의
`tests/test_download.py` 확장:
- interval 파라미터 존재 확인
- interval="1h" 시 파일명 `SPY_1h.parquet`
- interval="1h" 시 yfinance에 interval 전달
- interval="1h" + period="5y" → period="730d" 강제
- interval="1d" 기본값 시 기존 동작 유지
- CLI --interval 옵션 파싱

### Step 2: 구현
- `download.py`: download_symbol()에 interval 파라미터 추가
- 파일명: interval != "1d"이면 `{symbol}_{interval}.parquet`
- 1h일 때 period를 "730d"로 강제
- parse_args에 --interval 추가

---

## Phase 2: data_loader.py — interval 인식 로드

### Step 1: 테스트 정의
`tests/test_data_loader.py` 확장:
- load_single(symbol, interval="1h") 시 `SPY_1h.parquet` 로드
- load_single(symbol) 기본값 시 기존 `SPY.parquet` 로드
- load_multi(symbols, interval="1h") 동작

### Step 2: 구현
- `backtest/data_loader.py`: load_single/load_multi에 interval 파라미터
- 파일명 결정: `{symbol}_{interval}.parquet` (interval != "1d")

---

## Phase 3: metrics.py — Sharpe 연환산 계수 파라미터화

### Step 1: 테스트 정의
`tests/test_metrics.py` 확장:
- compute_metrics_fast(periods_per_year=252) 기존과 동일
- compute_metrics_fast(periods_per_year=1638) 다른 Sharpe 값
- compute_metrics()도 periods_per_year 지원
- 파라미터 없으면 기본값 252

### Step 2: 구현
- `backtest/metrics.py`: 두 함수에 periods_per_year=252 파라미터
- np.sqrt(252) → np.sqrt(periods_per_year)

---

## Phase 4: grid_search.py — hourly 데이터 연동

### Step 1: 테스트 정의
`tests/test_grid_search.py` 확장:
- _run_symbol: tf=="hourly" 시 hourly_df 사용
- run_full_grid_search: hourly_data 파라미터
- timeframes=["hourly"] 시 hourly_data에서 데이터
- hourly Sharpe에 periods_per_year=1638 전달
- hourly_data에 심볼 없으면 해당 tf 스킵

### Step 2: 구현
- `_run_symbol()`: hourly_df 파라미터 추가, tf=="hourly" 분기
- `run_grid_search()`: periods_per_year 파라미터 → compute_metrics_fast 전달
- `run_full_grid_search()`: hourly_data 파라미터 추가

---

## Phase 5: runner.py — CLI 통합 + 실행

### Step 1: 테스트 정의
`tests/test_runner.py` 확장:
- --timeframes daily,weekly,hourly 파싱
- run_full_analysis에서 hourly in timeframes 시 hourly 데이터 로드

### Step 2: 구현
- `backtest/runner.py`: run_full_analysis()에서 hourly 데이터 별도 로드
- load_multi(all_symbols, interval="1h") → hourly_data
- run_full_grid_search(data=data, hourly_data=hourly_data, ...)

### Step 3: 실제 실행
```bash
python download.py --interval 1h
python -m backtest.runner --full-report --timeframes daily,hourly --n-jobs 8 --progress
```

---

## 변경 파일 요약

| 파일 | 변경 | 하위호환 |
|------|------|---------|
| `download.py` | interval 파라미터, 파일명, 730d 강제 | O |
| `backtest/data_loader.py` | interval 파라미터 | O |
| `backtest/metrics.py` | periods_per_year 파라미터 | O |
| `backtest/grid_search.py` | hourly_df, hourly_data, periods_per_year | O |
| `backtest/runner.py` | hourly 데이터 로드 + 전달 | O |

## 검증

1. 기존 177개 테스트 전체 통과
2. 새 테스트 전체 통과
3. `python download.py --interval 1h` 실행하여 13종목 시간봉 다운로드
4. `--full-report --timeframes daily,hourly --n-jobs 8` 실행하여 그리드 서치 결과 확인
