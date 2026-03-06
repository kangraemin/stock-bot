# Phase 1 Step 1: download.py interval 테스트

## 테스트 케이스

| TC | 설명 | 결과 |
|----|------|------|
| TC-1 | download_symbol에 interval 파라미터 존재 | ✅ |
| TC-2 | interval='1h' 시 SPY_1h.parquet 파일명 | ✅ |
| TC-3 | interval='1d' 기본값 시 SPY.parquet 유지 | ✅ |
| TC-4 | interval='1h' 시 yfinance에 interval 전달 | ✅ |
| TC-5 | interval='1h' + period='5y' → period='730d' 강제 | ✅ |
| TC-6 | 시간봉 파일 캐시 동작 | ✅ |
| TC-7 | CLI --interval 옵션 파싱 | ✅ |
| TC-8 | CLI interval 기본값 1d | ✅ |

## 대상 파일
- tests/test_download.py (테스트 추가)
- download.py (구현 대상)
