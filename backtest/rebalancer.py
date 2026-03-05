"""포트폴리오 리밸런싱 로직"""


THRESHOLD = 0.02  # 2%p


def needs_rebalance(current_weights: dict[str, float], target_weights: dict[str, float]) -> bool:
    for sym in target_weights:
        diff = abs(current_weights.get(sym, 0) - target_weights[sym])
        if diff >= THRESHOLD:
            return True
    return False


def compute_target_weights_equal(symbols: list[str]) -> dict[str, float]:
    n = len(symbols)
    if n == 0:
        return {}
    w = 1.0 / n
    return {s: w for s in symbols}


def compute_target_weights_custom(weights: dict[str, float]) -> dict[str, float]:
    return dict(weights)


def should_rebalance_on_date(date, freq: str = "monthly") -> bool:
    if freq == "monthly":
        return date.day <= 5  # 월초 5일 이내
    if freq == "weekly":
        return date.weekday() == 0  # 월요일
    return False
