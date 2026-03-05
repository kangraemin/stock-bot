# Phase 2 - Step 3: Phase 2 테스트

## 목표
- Phase 2에서 변경한 모든 모듈의 단위 테스트 작성

## 변경 파일
- `tests/test_grid_search.py`
- `tests/test_data_loader.py`

## 테스트 항목 (TC 요약)

### Step 1 — resample_to_weekly (6 TCs, `tests/test_data_loader.py`)
| TC | 설명 |
|----|------|
| TC-1 | resample_to_weekly 반환 타입이 DataFrame |
| TC-2 | 주간 리샘플링 결과 행 수 감소 |
| TC-3 | OHLCV 컬럼 존재 확인 |
| TC-4 | Open=첫날, Close=마지막날 |
| TC-5 | High=주간 최고, Low=주간 최저 |
| TC-6 | Volume=주간 합계 |

### Step 2 — Grid Search 확장 + 병렬화 (8 TCs, `tests/test_grid_search.py`)
| TC | 설명 |
|----|------|
| TC-1 | DEFAULT_GRID 키 10개 |
| TC-2 | generate_param_combinations 49152 조합 |
| TC-3 | generate_param_combinations 결과가 dict 리스트 |
| TC-4 | run_full_grid_search 반환 타입 list |
| TC-5 | run_full_grid_search 결과 dict 키 포함 확인 |
| TC-6 | run_full_grid_search n_jobs 파라미터 지원 |
| TC-7 | run_full_grid_search top_n=5 결과 5개 |
| TC-8 | run_full_grid_search 결과 total_return 내림차순 |

### 검증 기준
- 전체 회귀 테스트 155/155 통과 (Phase 1 + Phase 2 포함)
