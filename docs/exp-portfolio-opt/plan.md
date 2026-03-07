# Experiment 4: Multi-Asset Portfolio Optimization

## 개요
~500K 조합의 멀티에셋 포트폴리오 최적화 실험. 2/3/4-asset 포트폴리오를 다양한 가중치와 리밸런싱 전략으로 백테스트.

## 개발 Phase

### Phase 1: `experiments/exp_portfolio_opt.py` 작성
단일 self-contained 파일. backtest/ 모듈 임포트 없이 numpy 기반 자체 구현.

#### 핵심 구조
1. **데이터 로딩**: parquet에서 Close 컬럼만 로드, 공통 날짜 인덱스 정렬
2. **포트폴리오 시뮬레이터**: numpy 기반 일별 시뮬레이션
   - shares * price → asset values
   - 리밸런싱 트리거 체크 (band / calendar)
   - 리밸런싱 시 0.25% 수수료 양방향
3. **조합 생성기**:
   - 2-asset: 200 pairs × 9 weights × 11 rebal = 19,800
   - 3-asset: 2,800 combos × 10 weights × 8 rebal = 224,000
   - 4-asset: 8,550 combos × 5 weights × 6 rebal = 256,500
4. **멀티프로세싱**: cpu_count 활용, 청크 단위 처리
5. **IS/OOS 분할**: 70%/30%
6. **메트릭 계산**: total_return, sharpe, maxdd, calmar, trades, rebal_count
7. **결과 저장**: results/portfolio_opt_results.csv
8. **요약 출력**: Top 20 by OOS Sharpe (2/3/4-asset 별도), Calmar, Sharpe-to-MaxDD

#### 주요 설계 결정
- Column: `Close` (대문자)
- 데이터 최소 500일 겹침 필요
- Band 리밸런싱: max(|current - target|) > threshold
- Calendar: monthly(월초), quarterly(분기초), semi_annual(6개월), annual(연초)
- B&H 비교: 동일 자산 동일 가중치 buy-and-hold
- Progress: 50,000 조합마다 출력
- Capital: 2000

### Phase 2: 실행 및 결과 확인
실행 후 CSV 저장, 요약 출력 확인.

## 변경 파일
- `experiments/exp_portfolio_opt.py` (신규)
- `results/portfolio_opt_results.csv` (실행 결과)
