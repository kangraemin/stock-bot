"""
실험 6: Walk-Forward Analysis
- Train 504bars(~2yr) / Test 126bars(~6mo) 슬라이딩 윈도우
- Train에서 BB+RSI 그리드 서치 → Test에 적용, 자산 이월
- Walk-Forward vs Fixed-Params vs B&H 비교
"""
import pandas as pd
import numpy as np
import os
from itertools import product

TOTAL_CASH = 10000.0
FEE_RATE = 0.0025

SYMBOLS = ["SOXL", "TQQQ", "SPXL", "TNA"]

TRAIN_DAYS = 504
TEST_DAYS = 126

BUY_GRID = [20, 25, 30, 35, 40]
SELL_GRID = [60, 65, 70, 75]
REBUY_GRID = [30, 40, 50, 55]


def rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def bollinger_upper(series, period=20, num_std=2):
    sma = series.rolling(period).mean()
    std = series.rolling(period).std()
    return sma + num_std * std


def run_backtest(close, rsi_vals, bb_vals, buy_rsi, sell_rsi, rebuy_rsi, init_cash=TOTAL_CASH):
    """Run BB+RSI state machine backtest. Returns (final_equity, n_buys, n_sells, max_dd_pct)."""
    n = len(close)
    cash = init_cash
    shares = 0.0
    state = 0
    n_buys = 0
    n_sells = 0
    peak_val = init_cash
    max_dd = 0.0

    for i in range(n):
        price = close[i]
        rv = rsi_vals[i]
        bb = bb_vals[i]
        if np.isnan(rv) or np.isnan(bb):
            val = cash + shares * price
            if val > peak_val:
                peak_val = val
            continue

        if state == 0:
            if rv < buy_rsi:
                shares = cash * (1 - FEE_RATE) / price
                cash = 0
                n_buys += 1
                state = 1
        elif state == 1:
            if rv > sell_rsi and price > bb:
                cash = shares * price * (1 - FEE_RATE)
                shares = 0
                n_sells += 1
                state = 2
        elif state == 2:
            if rv < rebuy_rsi:
                shares = cash * (1 - FEE_RATE) / price
                cash = 0
                n_buys += 1
                state = 1

        val = cash + shares * price
        if val > peak_val:
            peak_val = val
        dd = (val - peak_val) / peak_val
        if dd < max_dd:
            max_dd = dd

    final = cash + shares * close[-1]
    return final, n_buys, n_sells, round(max_dd * 100, 1)


def grid_search_train(close, rsi_vals, bb_vals):
    """Grid search on train window. Returns best (buy_rsi, sell_rsi, rebuy_rsi)."""
    best_ret = -np.inf
    best_params = (30, 70, 50)

    for br, sr, rr in product(BUY_GRID, SELL_GRID, REBUY_GRID):
        if br >= sr:
            continue
        final, _, _, _ = run_backtest(close, rsi_vals, bb_vals, br, sr, rr)
        ret = final / TOTAL_CASH - 1
        if ret > best_ret:
            best_ret = ret
            best_params = (br, sr, rr)

    return best_params


def walk_forward(symbol, close_series):
    """Run walk-forward analysis for one symbol."""
    rsi_vals = rsi(close_series, 14).values
    bb_vals = bollinger_upper(close_series, 20, 2).values
    close = close_series.values
    dates = close_series.index
    n = len(close)

    rows = []
    equity = TOTAL_CASH
    total_buys = 0
    total_sells = 0
    wf_peak = TOTAL_CASH
    wf_max_dd = 0.0
    win_num = 0

    start = 0
    while start + TRAIN_DAYS + TEST_DAYS <= n:
        train_end = start + TRAIN_DAYS
        test_end = train_end + TEST_DAYS

        # Train: grid search
        train_close = close[start:train_end]
        train_rsi = rsi_vals[start:train_end]
        train_bb = bb_vals[start:train_end]
        best_params = grid_search_train(train_close, train_rsi, train_bb)

        # Test: apply best params with carried equity
        test_close = close[train_end:test_end]
        test_rsi = rsi_vals[train_end:test_end]
        test_bb = bb_vals[train_end:test_end]
        final_eq, nb, ns, test_dd = run_backtest(
            test_close, test_rsi, test_bb,
            best_params[0], best_params[1], best_params[2],
            init_cash=equity,
        )

        total_buys += nb
        total_sells += ns

        # Track walk-forward drawdown
        if final_eq > wf_peak:
            wf_peak = final_eq
        dd_pct = (final_eq - wf_peak) / wf_peak * 100
        if dd_pct < wf_max_dd:
            wf_max_dd = dd_pct

        win_num += 1
        rows.append({
            "symbol": symbol,
            "window": win_num,
            "train_start": str(dates[start].date()),
            "train_end": str(dates[train_end - 1].date()),
            "test_start": str(dates[train_end].date()),
            "test_end": str(dates[test_end - 1].date()),
            "best_buy_rsi": best_params[0],
            "best_sell_rsi": best_params[1],
            "best_rebuy_rsi": best_params[2],
            "test_equity": round(final_eq, 2),
            "buys": nb,
            "sells": ns,
        })

        equity = final_eq
        start += TEST_DAYS

    return rows, equity, total_buys, total_sells, round(wf_max_dd, 1)


def run_fixed_params(close_series, test_start_idx, test_end_idx, buy_rsi, sell_rsi, rebuy_rsi):
    """Run fixed-params backtest over the same OOS range as walk-forward."""
    rsi_vals = rsi(close_series, 14).values
    bb_vals = bollinger_upper(close_series, 20, 2).values
    close = close_series.values

    sl = close[test_start_idx:test_end_idx]
    rv = rsi_vals[test_start_idx:test_end_idx]
    bv = bb_vals[test_start_idx:test_end_idx]
    final, nb, ns, mdd = run_backtest(sl, rv, bv, buy_rsi, sell_rsi, rebuy_rsi)
    ret = (final / TOTAL_CASH - 1) * 100
    return round(ret, 1), mdd, nb, ns


def run_bh(close_series, start_idx, end_idx):
    """Buy & hold over the same OOS range."""
    close = close_series.values
    shares = TOTAL_CASH * (1 - FEE_RATE) / close[start_idx]
    final = shares * close[end_idx - 1]
    return round((final / TOTAL_CASH - 1) * 100, 1)


def main():
    print("=" * 120)
    print("EXP 6: WALK-FORWARD ANALYSIS (Train 504 / Test 126)")
    print("=" * 120)

    all_rows = []

    # Fixed params from full-period grid search (exp1 best)
    FIXED_PARAMS = {
        "SOXL": (25, 60, 55),
        "TQQQ": (25, 65, 55),
        "SPXL": (30, 70, 55),
        "TNA": (35, 70, 50),
    }

    for symbol in SYMBOLS:
        path = f"data/{symbol}.parquet"
        if not os.path.exists(path):
            print(f"  [SKIP] {path} not found")
            continue

        df = pd.read_parquet(path).sort_index()
        close_series = df["close"]
        n = len(close_series)

        print(f"\n[{symbol}] {n} bars | {close_series.index[0].date()} ~ {close_series.index[-1].date()}")

        # Walk-forward
        rows, wf_equity, wf_buys, wf_sells, wf_mdd = walk_forward(symbol, close_series)
        wf_ret = round((wf_equity / TOTAL_CASH - 1) * 100, 1)

        # Determine OOS range (same as walk-forward test windows)
        n_windows = (n - TRAIN_DAYS) // TEST_DAYS
        oos_start = TRAIN_DAYS
        oos_end = TRAIN_DAYS + n_windows * TEST_DAYS
        if oos_end > n:
            oos_end = n

        # Fixed params over OOS range
        fp = FIXED_PARAMS.get(symbol, (30, 70, 50))
        fixed_ret, fixed_mdd, fixed_buys, fixed_sells = run_fixed_params(
            close_series, oos_start, oos_end, fp[0], fp[1], fp[2]
        )

        # B&H over OOS range
        bh_ret = run_bh(close_series, oos_start, oos_end)

        print(f"  OOS range: {close_series.index[oos_start].date()} ~ {close_series.index[oos_end-1].date()} ({oos_end - oos_start} bars, {n_windows} windows)")
        print(f"  Walk-Forward: {wf_ret:>+10,.1f}% | MaxDD {wf_mdd}% | {wf_buys}B/{wf_sells}S")
        print(f"  Fixed Params: {fixed_ret:>+10,.1f}% | MaxDD {fixed_mdd}% | {fixed_buys}B/{fixed_sells}S  (buy={fp[0]} sell={fp[1]} rebuy={fp[2]})")
        print(f"  Buy & Hold:   {bh_ret:>+10,.1f}%")
        print(f"  WF vs Fixed:  {wf_ret - fixed_ret:>+10,.1f}%")
        print(f"  WF vs B&H:    {wf_ret - bh_ret:>+10,.1f}%")

        # Summary row
        rows.append({
            "symbol": symbol,
            "window": "TOTAL",
            "train_start": "",
            "train_end": "",
            "test_start": str(close_series.index[oos_start].date()),
            "test_end": str(close_series.index[oos_end - 1].date()),
            "best_buy_rsi": "",
            "best_sell_rsi": "",
            "best_rebuy_rsi": "",
            "test_equity": round(wf_equity, 2),
            "buys": wf_buys,
            "sells": wf_sells,
            "wf_return_pct": wf_ret,
            "fixed_return_pct": fixed_ret,
            "bh_return_pct": bh_ret,
            "wf_max_dd_pct": wf_mdd,
        })

        all_rows.extend(rows)

    # Save
    os.makedirs("results", exist_ok=True)
    res_df = pd.DataFrame(all_rows)
    res_df.to_csv("results/exp6_walk_forward.csv", index=False)

    print(f"\n{'='*120}")
    print("SUMMARY: Walk-Forward vs Fixed vs B&H")
    print(f"{'='*120}")
    summary = res_df[res_df["window"] == "TOTAL"]
    for _, row in summary.iterrows():
        print(f"  {row['symbol']:>5s}: WF {row['wf_return_pct']:>+10,.1f}% (MaxDD {row['wf_max_dd_pct']}%, {row['buys']}B/{row['sells']}S) | "
              f"Fixed {row['fixed_return_pct']:>+10,.1f}% | B&H {row['bh_return_pct']:>+10,.1f}%")

    print(f"\nSaved: results/exp6_walk_forward.csv")


if __name__ == "__main__":
    main()
