"""
BB 하한 필터 추가 효과 백테스트
- A (현재 alert.py): RSI < buy_threshold → BUY, RSI > sell_threshold AND close > BB상단 → SELL
- B (BB 하한 추가): close < BB하한 AND RSI < buy_threshold → BUY, 동일 SELL 조건
"""

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd
from backtest.data_loader import load_single
from backtest.metrics import compute_metrics_fast


SYMBOLS = {
    "SOXL": {"buy_rsi": 25, "sell_rsi": 60},
    "TQQQ": {"buy_rsi": 25, "sell_rsi": 65},
    "SPXL": {"buy_rsi": 30, "sell_rsi": 70},
    "TNA":  {"buy_rsi": 35, "sell_rsi": 70},
    "QLD":  {"buy_rsi": 25, "sell_rsi": 70},
    "UWM":  {"buy_rsi": 25, "sell_rsi": 70},
    "QQQ":  {"buy_rsi": 25, "sell_rsi": 75},
}

PERIODS = {
    "Full":      (None, None),
    "Bear2022":  ("2022-01-01", "2022-12-31"),
    "Bull23-24": ("2023-01-01", "2024-12-31"),
}

CAPITAL = 2000
FEE = 0.0025
BB_PERIOD = 20
BB_STD = 2
RSI_PERIOD = 14


def calc_rsi(close: pd.Series) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / RSI_PERIOD, min_periods=RSI_PERIOD).mean()
    avg_loss = loss.ewm(alpha=1 / RSI_PERIOD, min_periods=RSI_PERIOD).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def calc_bb(close: pd.Series):
    sma = close.rolling(BB_PERIOD).mean()
    std = close.rolling(BB_PERIOD).std()
    return sma + BB_STD * std, sma - BB_STD * std


def run_backtest(close_arr, rsi_arr, bb_upper_arr, bb_lower_arr, buy_rsi, sell_rsi, use_bb_filter):
    n = len(close_arr)
    equity = np.full(n, CAPITAL, dtype=np.float64)
    cash = CAPITAL
    shares = 0.0
    trades = 0
    state = "CASH"  # CASH, HOLDING, WAIT_REBUY

    for i in range(1, n):
        price = close_arr[i]
        r = rsi_arr[i]
        bb_up = bb_upper_arr[i]
        bb_lo = bb_lower_arr[i]

        if np.isnan(r) or np.isnan(bb_up) or np.isnan(bb_lo):
            equity[i] = cash + shares * price
            continue

        if state == "CASH":
            buy_cond = r < buy_rsi
            if use_bb_filter:
                buy_cond = buy_cond and price < bb_lo
            if buy_cond:
                cost = cash * (1 - FEE)
                shares = cost / price
                cash = 0.0
                state = "HOLDING"
                trades += 1

        elif state == "HOLDING":
            if r > sell_rsi and price > bb_up:
                proceeds = shares * price * (1 - FEE)
                cash = proceeds
                shares = 0.0
                state = "WAIT_REBUY"
                trades += 1

        elif state == "WAIT_REBUY":
            # rebuy는 원래 alert.py에서 rebuy_rsi 사용하지만,
            # 이 실험에서는 buy_rsi와 동일 조건으로 재매수
            buy_cond = r < buy_rsi
            if use_bb_filter:
                buy_cond = buy_cond and price < bb_lo
            if buy_cond:
                cost = cash * (1 - FEE)
                shares = cost / price
                cash = 0.0
                state = "HOLDING"
                trades += 1

        equity[i] = cash + shares * price

    return equity, trades


def buy_and_hold_return(close_arr):
    if len(close_arr) < 2:
        return 0.0
    return (close_arr[-1] / close_arr[0]) - 1


def main():
    rows = []

    for symbol, params in SYMBOLS.items():
        for period_name, (start, end) in PERIODS.items():
            try:
                df = load_single(symbol, start_date=start, end_date=end)
            except FileNotFoundError:
                print(f"SKIP {symbol}: no data")
                continue

            if len(df) < BB_PERIOD + RSI_PERIOD:
                continue

            close = df["close"]
            rsi_s = calc_rsi(close)
            bb_upper, bb_lower = calc_bb(close)

            close_arr = close.values.astype(np.float64)
            rsi_arr = rsi_s.values.astype(np.float64)
            bb_upper_arr = bb_upper.values.astype(np.float64)
            bb_lower_arr = bb_lower.values.astype(np.float64)
            dates_arr = df.index.values

            bh_ret = buy_and_hold_return(close_arr)

            for label, use_bb in [("A_RSI_only", False), ("B_BB_filter", True)]:
                equity, trades = run_backtest(
                    close_arr, rsi_arr, bb_upper_arr, bb_lower_arr,
                    params["buy_rsi"], params["sell_rsi"], use_bb,
                )
                m = compute_metrics_fast(equity, dates_arr, trades)
                rows.append({
                    "symbol": symbol,
                    "period": period_name,
                    "strategy": label,
                    "total_return": m["total_return"],
                    "ann_return": m["annualized_return"],
                    "max_dd": m["max_drawdown"],
                    "sharpe": m["sharpe_ratio"],
                    "calmar": m["calmar_ratio"],
                    "trades": m["total_trades"],
                    "bh_return": bh_ret,
                    "vs_bh": m["total_return"] - bh_ret,
                })

    result_df = pd.DataFrame(rows)

    # 콘솔 출력
    pd.set_option("display.max_columns", 20)
    pd.set_option("display.width", 200)
    pd.set_option("display.float_format", lambda x: f"{x:.4f}")

    print("\n" + "=" * 120)
    print("BB 하한 필터 추가 효과 비교 (A=RSI only vs B=BB+RSI)")
    print("=" * 120)

    for period_name in PERIODS:
        print(f"\n--- {period_name} ---")
        subset = result_df[result_df["period"] == period_name].copy()
        fmt = subset.to_string(index=False)
        print(fmt)

    # A vs B 비교 요약
    print("\n" + "=" * 120)
    print("A vs B 직접 비교 (B - A 차이)")
    print("=" * 120)

    pivot_rows = []
    for symbol in SYMBOLS:
        for period_name in PERIODS:
            a = result_df[(result_df["symbol"] == symbol) & (result_df["period"] == period_name) & (result_df["strategy"] == "A_RSI_only")]
            b = result_df[(result_df["symbol"] == symbol) & (result_df["period"] == period_name) & (result_df["strategy"] == "B_BB_filter")]
            if a.empty or b.empty:
                continue
            a = a.iloc[0]
            b = b.iloc[0]
            pivot_rows.append({
                "symbol": symbol,
                "period": period_name,
                "A_ret": a["total_return"],
                "B_ret": b["total_return"],
                "diff_ret": b["total_return"] - a["total_return"],
                "A_dd": a["max_dd"],
                "B_dd": b["max_dd"],
                "diff_dd": b["max_dd"] - a["max_dd"],
                "A_sharpe": a["sharpe"],
                "B_sharpe": b["sharpe"],
                "A_trades": a["trades"],
                "B_trades": b["trades"],
            })

    if pivot_rows:
        pivot_df = pd.DataFrame(pivot_rows)
        print(pivot_df.to_string(index=False))

        # 통계 요약
        wins = (pivot_df["diff_ret"] > 0).sum()
        total = len(pivot_df)
        avg_diff = pivot_df["diff_ret"].mean()
        avg_dd_diff = pivot_df["diff_dd"].mean()
        print(f"\nBB필터 우위: {wins}/{total} ({wins/total*100:.0f}%)")
        print(f"평균 수익률 차이: {avg_diff*100:+.2f}%p")
        print(f"평균 MDD 차이: {avg_dd_diff*100:+.2f}%p (양수=B가 덜 빠짐)")

    # CSV 저장
    out_path = pathlib.Path(__file__).resolve().parent.parent / "results" / "quant_bb_filter_results.csv"
    result_df.to_csv(out_path, index=False)
    print(f"\nCSV 저장: {out_path}")


if __name__ == "__main__":
    main()
