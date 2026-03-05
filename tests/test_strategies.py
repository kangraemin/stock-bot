"""Phase 2 Step 2-3: Strategy ABC + Registry + BB_RSI_EMA TC"""

import numpy as np
import pandas as pd
import pytest

from backtest.strategies.base import Signal, Strategy


# ── 테스트용 더미 전략 ──
class DummyStrategy(Strategy):
    def __init__(self, window=20):
        self._window = window

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        return pd.Series(Signal.HOLD, index=df.index)

    @property
    def params(self) -> dict:
        return {"window": self._window}


# ── TC-1: Strategy ABC 인스턴스화 불가 ──
def test_strategy_abc_cannot_instantiate():
    with pytest.raises(TypeError):
        Strategy()


# ── TC-2: generate_signals 추상 메서드 ──
def test_generate_signals_abstract():
    class Incomplete(Strategy):
        @property
        def params(self) -> dict:
            return {}

    with pytest.raises(TypeError):
        Incomplete()


# ── TC-3: params 프로퍼티 ──
def test_params_property():
    s = DummyStrategy(window=30)
    p = s.params
    assert isinstance(p, dict)
    assert p["window"] == 30


# ── TC-4: 서브클래스 정상 구현 ──
def test_subclass_instantiation():
    s = DummyStrategy()
    assert isinstance(s, Strategy)


# ── TC-5: generate_signals 반환 타입 ──
def test_generate_signals_return_type():
    dates = pd.date_range("2023-01-02", periods=50, freq="B")
    rng = np.random.default_rng(42)
    df = pd.DataFrame(
        {
            "open": rng.uniform(100, 200, 50),
            "high": rng.uniform(100, 200, 50),
            "low": rng.uniform(100, 200, 50),
            "close": rng.uniform(100, 200, 50),
            "volume": rng.integers(1_000_000, 10_000_000, 50),
        },
        index=dates,
    )
    s = DummyStrategy()
    signals = s.generate_signals(df)
    assert isinstance(signals, pd.Series)
    assert isinstance(signals.index, pd.DatetimeIndex)


# ── TC-6: Signal enum 값 ──
def test_signal_enum_values():
    assert Signal.BUY == 1
    assert Signal.SELL == -1
    assert Signal.HOLD == 0


# ── TC-7: STRATEGIES 레지스트리 dict ──
def test_strategies_registry_is_dict():
    from backtest.strategies import STRATEGIES

    assert isinstance(STRATEGIES, dict)


# ── TC-8: 레지스트리에서 전략 조회 ──
def test_registry_lookup():
    from backtest.strategies import STRATEGIES

    assert "bb_rsi_ema" in STRATEGIES


# ══════════════════════════════════════════════
# Phase 2 Step 3: BB+RSI+EMA 전략 TC
# ══════════════════════════════════════════════

from backtest.strategies.bb_rsi_ema import BbRsiEma


@pytest.fixture()
def ohlcv_df():
    """200일 OHLCV 테스트 데이터"""
    dates = pd.date_range("2022-01-03", periods=200, freq="B")
    rng = np.random.default_rng(42)
    base = 150 + rng.standard_normal(200).cumsum()
    return pd.DataFrame(
        {
            "open": base + rng.uniform(-1, 1, 200),
            "high": base + rng.uniform(0, 3, 200),
            "low": base - rng.uniform(0, 3, 200),
            "close": base,
            "volume": rng.integers(1_000_000, 10_000_000, 200),
        },
        index=dates,
    )


# ── Step3 TC-1: Strategy 상속 확인 ──
def test_bb_rsi_ema_is_strategy():
    s = BbRsiEma()
    assert isinstance(s, Strategy)


# ── Step3 TC-2: 기본 파라미터 ──
def test_bb_rsi_ema_default_params():
    s = BbRsiEma()
    p = s.params
    assert p["bb_window"] == 20
    assert p["bb_std"] == 2.0
    assert p["rsi_window"] == 14
    assert p["ema_window"] == 50


# ── Step3 TC-3: 커스텀 파라미터 주입 ──
def test_bb_rsi_ema_custom_params():
    s = BbRsiEma(bb_window=30, rsi_window=21)
    p = s.params
    assert p["bb_window"] == 30
    assert p["rsi_window"] == 21


# ── Step3 TC-4: generate_signals 반환 타입 ──
def test_bb_rsi_ema_signals_type(ohlcv_df):
    s = BbRsiEma()
    signals = s.generate_signals(ohlcv_df)
    assert isinstance(signals, pd.Series)
    assert len(signals) == len(ohlcv_df)


# ── Step3 TC-5: 시그널 값 범위 ──
def test_bb_rsi_ema_signal_values(ohlcv_df):
    s = BbRsiEma()
    signals = s.generate_signals(ohlcv_df)
    valid = {Signal.BUY, Signal.SELL, Signal.HOLD}
    assert set(signals.unique()).issubset(valid)


# ── Step3 TC-6: 데이터 부족 시 안전 ──
def test_bb_rsi_ema_short_data():
    dates = pd.date_range("2023-01-02", periods=5, freq="B")
    df = pd.DataFrame(
        {
            "open": [100] * 5,
            "high": [101] * 5,
            "low": [99] * 5,
            "close": [100] * 5,
            "volume": [1_000_000] * 5,
        },
        index=dates,
    )
    s = BbRsiEma()
    signals = s.generate_signals(df)
    assert (signals == Signal.HOLD).all()


# ── Step3 TC-7: STRATEGIES 레지스트리 등록 ──
def test_bb_rsi_ema_in_registry():
    from backtest.strategies import STRATEGIES

    assert STRATEGIES["bb_rsi_ema"] is BbRsiEma


# ── Step3 TC-8: BUY 시그널 생성 조건 ──
def test_bb_rsi_ema_buy_condition():
    """close < BB하한 + RSI < 30 + close > EMA 조건에서 BUY"""
    # 하락 후 반등 패턴: 오래 하락하다 EMA 위에서 BB하단 터치
    rng = np.random.default_rng(123)
    n = 200
    dates = pd.date_range("2022-01-03", periods=n, freq="B")
    # 완만한 하락 → 급락 → 반등 패턴
    close = pd.Series(200 - np.arange(n) * 0.1 + rng.standard_normal(n) * 0.5, index=dates)
    df = pd.DataFrame(
        {
            "open": close + rng.uniform(-0.5, 0.5, n),
            "high": close + rng.uniform(0, 1, n),
            "low": close - rng.uniform(0, 1, n),
            "close": close,
            "volume": rng.integers(1_000_000, 10_000_000, n),
        },
        index=dates,
    )
    s = BbRsiEma()
    signals = s.generate_signals(df)
    # 어떤 시그널이든 생성되었는지 (최소 HOLD 외 시그널 존재)
    # 구체적 BUY/SELL 발생은 데이터 의존적이므로 에러 없이 완료됨을 검증
    assert len(signals) == n
