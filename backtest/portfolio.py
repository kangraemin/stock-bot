"""멀티 포지션 포트폴리오 관리"""

from config import FeeModel


class Portfolio:
    def __init__(self, capital: float, fee_rate: float = FeeModel.STANDARD):
        self.cash = capital
        self.positions: dict[str, float] = {}
        self.trade_log: list[dict] = []
        self.equity_curve: list[dict] = []
        self._fee_rate = float(fee_rate)

    @property
    def trade_count(self) -> int:
        return len(self.trade_log)

    def buy(self, symbol: str, price: float, qty: float) -> bool:
        cost = price * qty * (1 + self._fee_rate)
        if cost > self.cash:
            return False
        self.cash -= cost
        self.positions[symbol] = self.positions.get(symbol, 0) + qty
        self.trade_log.append(
            {"action": "buy", "symbol": symbol, "price": price, "qty": qty, "cost": cost}
        )
        return True

    def sell(self, symbol: str, price: float, qty: float) -> bool:
        if self.positions.get(symbol, 0) < qty:
            return False
        revenue = price * qty * (1 - self._fee_rate)
        self.cash += revenue
        self.positions[symbol] -= qty
        if self.positions[symbol] == 0:
            del self.positions[symbol]
        self.trade_log.append(
            {"action": "sell", "symbol": symbol, "price": price, "qty": qty, "revenue": revenue}
        )
        return True

    def get_total_equity(self, prices: dict[str, float]) -> float:
        position_value = sum(
            prices.get(sym, 0) * qty for sym, qty in self.positions.items()
        )
        return self.cash + position_value

    def get_weights(self, prices: dict[str, float]) -> dict[str, float]:
        total = self.get_total_equity(prices)
        if total == 0:
            return {}
        weights = {}
        for sym, qty in self.positions.items():
            weights[sym] = (prices.get(sym, 0) * qty) / total
        return weights

    def update_equity(self, date: str, prices: dict[str, float]) -> None:
        equity = self.get_total_equity(prices)
        self.equity_curve.append({"date": date, "equity": equity})
