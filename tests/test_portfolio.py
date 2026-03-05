"""Phase 3 Step 1: Portfolio 클래스 TC"""

import pytest

from backtest.portfolio import Portfolio
from config import FeeModel


@pytest.fixture()
def pf():
    return Portfolio(capital=2000, fee_rate=FeeModel.STANDARD)


# ── TC-1: Portfolio 초기화 ──
def test_portfolio_init(pf):
    assert pf.cash == 2000
    assert pf.positions == {}


# ── TC-2: buy 수수료 차감 ──
def test_buy_fee_deduction(pf):
    result = pf.buy("SPY", price=100, qty=10)
    assert result is True
    expected_cost = 100 * 10 * (1 + FeeModel.STANDARD)
    assert pf.cash == pytest.approx(2000 - expected_cost)
    assert pf.positions["SPY"] == 10


# ── TC-3: sell 수수료 차감 ──
def test_sell_fee_deduction(pf):
    pf.buy("SPY", price=100, qty=10)
    cash_before = pf.cash
    pf.sell("SPY", price=110, qty=5)
    expected_revenue = 110 * 5 * (1 - FeeModel.STANDARD)
    assert pf.cash == pytest.approx(cash_before + expected_revenue)
    assert pf.positions["SPY"] == 5


# ── TC-4: buy 잔고 부족 ──
def test_buy_insufficient_cash(pf):
    result = pf.buy("SPY", price=100, qty=100)
    assert result is False
    assert pf.positions.get("SPY", 0) == 0


# ── TC-5: sell 미보유 종목 ──
def test_sell_no_position(pf):
    result = pf.sell("SPY", price=100, qty=1)
    assert result is False


# ── TC-6: get_total_equity ──
def test_get_total_equity(pf):
    pf.buy("SPY", price=100, qty=10)
    prices = {"SPY": 110}
    equity = pf.get_total_equity(prices)
    assert equity == pytest.approx(pf.cash + 110 * 10)


# ── TC-7: get_weights ──
def test_get_weights(pf):
    pf.buy("SPY", price=100, qty=5)
    pf.buy("QQQ", price=50, qty=10)
    prices = {"SPY": 100, "QQQ": 50}
    weights = pf.get_weights(prices)
    # weights는 포지션 비중 (현금 제외), 합 <= 1.0
    assert sum(weights.values()) <= 1.0 + 1e-9
    assert "SPY" in weights
    assert "QQQ" in weights


# ── TC-8: trade_log 기록 ──
def test_trade_log(pf):
    pf.buy("SPY", price=100, qty=10)
    pf.sell("SPY", price=110, qty=5)
    assert len(pf.trade_log) == 2
    assert pf.trade_log[0]["action"] == "buy"
    assert pf.trade_log[1]["action"] == "sell"


# ── TC-9: trade_count ──
def test_trade_count(pf):
    pf.buy("SPY", price=100, qty=10)
    pf.sell("SPY", price=110, qty=5)
    pf.buy("QQQ", price=50, qty=10)
    assert pf.trade_count == 3


# ── TC-10: update_equity ──
def test_update_equity(pf):
    pf.buy("SPY", price=100, qty=10)
    prices = {"SPY": 105}
    pf.update_equity("2023-01-03", prices)
    assert len(pf.equity_curve) == 1
    assert pf.equity_curve[0]["equity"] == pytest.approx(pf.cash + 105 * 10)
