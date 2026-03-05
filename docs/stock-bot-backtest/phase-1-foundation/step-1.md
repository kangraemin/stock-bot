# Phase 1 Step 1: config.py + requirements.txt + .gitignore

## 목표
프로젝트 전역 설정, 의존성, gitignore 설정

## 구현 대상
- `config.py`: SYMBOLS_BASE, SYMBOLS_3X, LEVERAGE_MAP, FeeModel, 슬리피지, 자본금, 포트폴리오 프리셋
- `requirements.txt`: yfinance, pandas, numpy, ta, matplotlib, pyarrow, pytest
- `.gitignore`: data/, __pycache__, .venv, backtest/output/

## TC

| TC | 설명 | 검증 |
|----|------|------|
| TC-01 | SYMBOLS_BASE는 8개 종목 | len(SYMBOLS_BASE) == 8, 필수 종목 포함 |
| TC-02 | SYMBOLS_3X는 5개 종목 | len(SYMBOLS_3X) == 5, 필수 종목 포함 |
| TC-03 | LEVERAGE_MAP 키는 SYMBOLS_3X와 일치 | set(LEVERAGE_MAP.keys()) == set(SYMBOLS_3X) |
| TC-04 | LEVERAGE_MAP 값은 올바른 기초자산 | TQQQ->QQQ, SPXL->SPY 등 |
| TC-05 | FeeModel STANDARD = 0.0025 | FeeModel.STANDARD == 0.0025 |
| TC-06 | FeeModel EVENT = 0.0009 | FeeModel.EVENT == 0.0009 |
| TC-07 | 슬리피지 = 0.001 | SLIPPAGE == 0.001 |
| TC-08 | 자본금 = 2000 | CAPITAL == 2000 |
| TC-09 | PRESET_GROWTH 5종목 | 성장주 종목 확인 |
| TC-10 | PRESET_SAFE 4종목 | 안전주 종목 확인 |
| TC-11 | PRESET_MIXED 비중 합 100% | sum(weights) == 1.0 |
| TC-12 | PRESET_ALL_3X 균등 배분 | 모두 SYMBOLS_3X 소속, 균등 비중 |
| TC-13 | requirements.txt 필수 패키지 포함 | yfinance, pandas, numpy, ta, matplotlib, pyarrow, pytest |
| TC-14 | .gitignore 필수 패턴 포함 | data/, __pycache__, .venv, backtest/output/ |

## 결과: ✅ 19 passed (2026-03-05)
