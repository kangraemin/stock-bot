"""손절/시간스탑 메커니즘 효과 백테스트

7가지 변형을 4종목 × 2기간으로 테스트하여 MaxDD 개선 효과를 검증한다.
"""

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd
from backtest.data_loader import load_single
from backtest.metrics import compute_metrics_fast

# ── 종목별 파라미터 ──
SYMBOLS = {
    "SOXL": {"buy_rsi": 25, "sell_rsi": 60},
    "TQQQ": {"buy_rsi": 25, "sell_rsi": 65},
    "SPXL": {"buy_rsi": 30, "sell_rsi": 70},
    "TNA":  {"buy_rsi": 35, "sell_rsi": 70},
}

CAPITAL = 2000.0
FEE_RATE = 0.0025
RSI_PERIOD = 14
BB_PERIOD = 20
BB_STD = 2.0
ATR_PERIOD = 14

PERIODS = {
    "Full": (None, None),
    "Bear2022": ("2022-01-01", "2022-12-31"),
}


def compute_rsi(close: pd.Series, period: int = RSI_PERIOD) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period).mean()
    rs = avg_gain / avg_loss
    return 100 - 100 / (1 + rs)


def compute_bb_upper(close: pd.Series, period: int = BB_PERIOD, num_std: float = BB_STD) -> pd.Series:
    sma = close.rolling(period).mean()
    std = close.rolling(period).std()
    return sma + num_std * std


def compute_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = ATR_PERIOD) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def run_backtest(df: pd.DataFrame, buy_rsi: int, sell_rsi: int, variant: str) -> dict:
    """단일 종목 백테스트 루프. variant에 따라 손절 조건이 달라진다."""
    close = df["close"].values
    high = df["high"].values
    low = df["low"].values

    rsi = compute_rsi(df["close"], RSI_PERIOD).values
    bb_upper = compute_bb_upper(df["close"], BB_PERIOD, BB_STD).values
    atr = compute_atr(df["high"], df["low"], df["close"], ATR_PERIOD).values

    n = len(close)
    equity = np.full(n, CAPITAL, dtype=np.float64)
    cash = CAPITAL
    shares = 0.0
    entry_price = 0.0
    entry_idx = 0
    holding_high = 0.0
    total_trades = 0

    for i in range(1, n):
        # 보유 중 고점 추적
        if shares > 0:
            if close[i] > holding_high:
                holding_high = close[i]

        # ── 매도 조건 체크 ──
        if shares > 0:
            sell = False
            # 기본 시그널: RSI > sell_rsi AND close > BB upper
            if rsi[i] > sell_rsi and close[i] > bb_upper[i]:
                sell = True

            # 변형별 손절 조건
            if variant == "SL-15%":
                if close[i] <= entry_price * 0.85:
                    sell = True
            elif variant == "SL-20%":
                if close[i] <= entry_price * 0.80:
                    sell = True
            elif variant == "Time-40":
                if (i - entry_idx) >= 40:
                    sell = True
            elif variant == "Time-60":
                if (i - entry_idx) >= 60:
                    sell = True
            elif variant == "ATR-Trail":
                if not np.isnan(atr[i]) and holding_high > 0:
                    trail_stop = holding_high - 2 * atr[i]
                    if close[i] <= trail_stop:
                        sell = True
            elif variant == "Combined":
                if close[i] <= entry_price * 0.80:
                    sell = True
                if (i - entry_idx) >= 60:
                    sell = True

            if sell:
                proceeds = shares * close[i] * (1 - FEE_RATE)
                cash += proceeds
                shares = 0.0
                total_trades += 1

        # ── 매수 조건 체크 ──
        if shares == 0 and not np.isnan(rsi[i]):
            if rsi[i] < buy_rsi:
                invest = cash * 0.95
                cost_per_share = close[i] * (1 + FEE_RATE)
                shares = invest / cost_per_share
                cash -= invest
                entry_price = close[i]
                entry_idx = i
                holding_high = close[i]
                total_trades += 1

        equity[i] = cash + shares * close[i]

    dates = df.index.values.astype("datetime64[ns]")
    metrics = compute_metrics_fast(equity, dates, total_trades)
    return metrics


def main():
    all_results = []

    for symbol, params in SYMBOLS.items():
        for period_name, (start, end) in PERIODS.items():
            try:
                df = load_single(symbol, start_date=start, end_date=end)
            except FileNotFoundError:
                print(f"  [SKIP] {symbol} data not found")
                continue

            if len(df) < 50:
                print(f"  [SKIP] {symbol} {period_name}: insufficient data ({len(df)} rows)")
                continue

            # B&H 기준
            bh_return = (df["close"].iloc[-1] - df["close"].iloc[0]) / df["close"].iloc[0]

            variants = ["Baseline", "SL-15%", "SL-20%", "Time-40", "Time-60", "ATR-Trail", "Combined"]
            for variant in variants:
                metrics = run_backtest(df, params["buy_rsi"], params["sell_rsi"], variant)
                metrics["symbol"] = symbol
                metrics["period"] = period_name
                metrics["variant"] = variant
                metrics["bh_return"] = bh_return
                metrics["vs_bh"] = metrics["total_return"] - bh_return
                all_results.append(metrics)

    results_df = pd.DataFrame(all_results)

    # ── 콘솔 출력 ──
    print("\n" + "=" * 100)
    print("손절/시간스탑 메커니즘 백테스트 결과")
    print("=" * 100)

    for period_name in PERIODS:
        print(f"\n{'─' * 100}")
        print(f"  Period: {period_name}")
        print(f"{'─' * 100}")
        print(f"{'Symbol':<8} {'Variant':<12} {'Return':>10} {'AnnRet':>10} {'MaxDD':>10} {'Sharpe':>8} {'Trades':>7} {'vs B&H':>10}")
        print(f"{'─' * 8} {'─' * 12} {'─' * 10} {'─' * 10} {'─' * 10} {'─' * 8} {'─' * 7} {'─' * 10}")

        subset = results_df[results_df["period"] == period_name]
        for symbol in SYMBOLS:
            sym_data = subset[subset["symbol"] == symbol]
            for _, row in sym_data.iterrows():
                print(
                    f"{row['symbol']:<8} {row['variant']:<12} "
                    f"{row['total_return']:>9.1%} {row['annualized_return']:>9.1%} "
                    f"{row['max_drawdown']:>9.1%} {row['sharpe_ratio']:>7.2f} "
                    f"{row['total_trades']:>7} {row['vs_bh']:>9.1%}"
                )
            print()

    # ── 핵심 인사이트 ──
    print("\n" + "=" * 100)
    print("핵심 인사이트")
    print("=" * 100)

    # Full 기간 기준 MaxDD 개선 비교
    full = results_df[results_df["period"] == "Full"]
    if not full.empty:
        for symbol in SYMBOLS:
            sym = full[full["symbol"] == symbol]
            if sym.empty:
                continue
            baseline = sym[sym["variant"] == "Baseline"]
            if baseline.empty:
                continue
            bl_mdd = baseline.iloc[0]["max_drawdown"]
            print(f"\n[{symbol}] Baseline MaxDD: {bl_mdd:.1%}")
            for _, row in sym.iterrows():
                if row["variant"] == "Baseline":
                    continue
                mdd_diff = row["max_drawdown"] - bl_mdd
                ret_diff = row["total_return"] - baseline.iloc[0]["total_return"]
                better = "개선" if row["max_drawdown"] > bl_mdd else "악화"
                print(
                    f"  {row['variant']:<12}: MaxDD {row['max_drawdown']:>7.1%} "
                    f"({mdd_diff:+.1%} {better}), "
                    f"Return {row['total_return']:>7.1%} ({ret_diff:+.1%})"
                )

    # Bear 2022 기간
    bear = results_df[results_df["period"] == "Bear2022"]
    if not bear.empty:
        print(f"\n{'─' * 60}")
        print("Bear 2022 구간 MaxDD 개선 효과:")
        for symbol in SYMBOLS:
            sym = bear[bear["symbol"] == symbol]
            if sym.empty:
                continue
            baseline = sym[sym["variant"] == "Baseline"]
            if baseline.empty:
                continue
            bl_mdd = baseline.iloc[0]["max_drawdown"]
            best = sym.loc[sym["max_drawdown"].idxmax()]
            print(
                f"  {symbol}: Baseline MaxDD {bl_mdd:.1%} → "
                f"Best={best['variant']} MaxDD {best['max_drawdown']:.1%}"
            )

    # 종합 결론
    print(f"\n{'─' * 60}")
    print("종합 결론:")
    if not full.empty:
        # 전 종목 평균 MaxDD 개선
        variants = ["SL-15%", "SL-20%", "Time-40", "Time-60", "ATR-Trail", "Combined"]
        for v in variants:
            v_data = full[full["variant"] == v]
            bl_data = full[full["variant"] == "Baseline"]
            if v_data.empty or bl_data.empty:
                continue
            avg_mdd_improve = (v_data["max_drawdown"].values - bl_data["max_drawdown"].values).mean()
            avg_ret_diff = (v_data["total_return"].values - bl_data["total_return"].values).mean()
            print(f"  {v:<12}: 평균 MaxDD 변화 {avg_mdd_improve:+.1%}, 평균 수익률 변화 {avg_ret_diff:+.1%}")

    # ── CSV 저장 ──
    results_dir = pathlib.Path(__file__).resolve().parent.parent / "results"
    results_dir.mkdir(exist_ok=True)
    csv_path = results_dir / "prop_stoploss_results.csv"
    results_df.to_csv(csv_path, index=False)
    print(f"\n결과 저장: {csv_path}")


if __name__ == "__main__":
    main()
