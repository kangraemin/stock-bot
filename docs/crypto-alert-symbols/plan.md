# 코인 관련 종목 7개 alert.py buy_only 추가

## Context

백테스트 결과 코인 관련 종목은 RSI DCA(분할매수)가 B&H 대비 압도적 우위 확인됨 (full 기간 67% 승률, MSTR +1,081%p). 변동성이 극단적이라 RSI 저점 매수가 유효. 매도 시그널 없이 매수 타이밍만 제공 (buy_only 모드).

## 변경 파일

- `alert.py` — SYMBOLS dict에 7종목 추가
- `tests/test_alert_buy_only.py` — 신규 종목 테스트 추가

## Phase 1: alert.py SYMBOLS 추가

`alert.py` 라인 46~50 부근, 기존 buy_only 종목(GGLL, NVDA) 아래에 7종목 추가:

```python
"MSTR": {"group": "비트코인", "buy_rsi": 30, "sell_rsi": None, "rebuy_rsi": None,
         "desc": "MicroStrategy (비트코인 대리)", "buy_only": True},
"HOOD": {"group": "핀테크", "buy_rsi": 30, "sell_rsi": None, "rebuy_rsi": None,
         "desc": "Robinhood", "buy_only": True},
"MARA": {"group": "비트마이닝", "buy_rsi": 30, "sell_rsi": None, "rebuy_rsi": None,
         "desc": "Marathon Digital", "buy_only": True},
"COIN": {"group": "크립토", "buy_rsi": 30, "sell_rsi": None, "rebuy_rsi": None,
         "desc": "Coinbase", "buy_only": True},
"WGMI": {"group": "비트마이닝", "buy_rsi": 30, "sell_rsi": None, "rebuy_rsi": None,
         "desc": "비트코인 채굴 ETF", "buy_only": True},
"CLSK": {"group": "비트마이닝", "buy_rsi": 30, "sell_rsi": None, "rebuy_rsi": None,
         "desc": "CleanSpark", "buy_only": True},
"BITQ": {"group": "크립토", "buy_rsi": 25, "sell_rsi": None, "rebuy_rsi": None,
         "desc": "크립토 인덱스 ETF", "buy_only": True},
```

buy_rsi 값은 백테스트 결과 기반: 대부분 30, BITQ만 25 (인덱스 ETF이므로 보수적).

## Phase 2: 테스트 추가

`tests/test_alert_buy_only.py`의 기존 패턴을 따라:
- `TestSymbolsConfig` 클래스에 7종목 설정 검증 테스트 추가
- 신규 종목이 buy_only=True, sell_rsi=None, rebuy_rsi=None 확인

## 검증

1. `pytest tests/test_alert_buy_only.py -v` — buy_only 테스트 통과
2. `pytest tests/ -v` — 전체 테스트 통과 (기존 177개 + 신규)
3. `python -c "from alert import SYMBOLS; print(len(SYMBOLS))"` — 16개 확인 (기존 9 + 신규 7)
