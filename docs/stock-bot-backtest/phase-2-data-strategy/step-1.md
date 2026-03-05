# Phase 2 Step 1: data_loader.py

## 목표
Parquet 파일 로드 및 날짜 필터링

## 구현 대상
- `backtest/data_loader.py`: Parquet 로드, 날짜 필터, load_multi(symbols) -> dict

## TC

| TC | 설명 | 검증 |
|----|------|------|
| TC-1 | load_single 정상 로드 | DataFrame 반환, 컬럼 open/high/low/close/volume 포함 |
| TC-2 | load_single 파일 없음 | FileNotFoundError 발생 |
| TC-3 | load_single 날짜 필터 (start+end) | 범위 내 데이터만 반환 |
| TC-4 | load_single start만 지정 | start 이후 데이터만 |
| TC-5 | load_single end만 지정 | end 이전 데이터만 |
| TC-6 | load_single 인덱스 타입 | DatetimeIndex |
| TC-7 | load_multi 정상 | dict[str, DataFrame] 반환 |
| TC-8 | load_multi 빈 리스트 | 빈 dict 반환 |
| TC-9 | load_multi 일부 심볼 없음 | 해당 심볼 skip, warning 로그 |
| TC-10 | load_multi 날짜 필터 전파 | 각 심볼에 start/end 적용 |

## 결과 ✅
- 10/10 TC 통과 (pytest)
