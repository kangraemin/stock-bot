"""
실험 9: Correlation-Based Portfolio
- 4종목 롤링 상관행렬 → 최소분산/역변동성 비중
- 월별 리밸런싱
- 비교: equal weight, inverse-vol, min-variance, 개별 B&H
"""
import pandas as pd
import numpy as np
import os

TOTAL_CASH = 10000.0
FEE_RATE = 0.0025

SYMBOLS = ["SOXL", "TQQQ", "SPXL", "TNA"]
CORR_WINDOWS = [60, 120, 252]
REBALANCE_FREQ = 21  # monthly


def min_variance_weights(cov_matrix):
    """최소분산 포트폴리오 비중 (closed-form)"""
    try:
        inv_cov = np.linalg.inv(cov_matrix)
        ones = np.ones(len(cov_matrix))
        w = inv_cov @ ones / (ones @ inv_cov @ ones)
        # Clip negative weights, renormalize
        w = np.maximum(w, 0)
        if w.sum() > 0:
            w = w / w.sum()
        else:
            w = np.ones(len(cov_matrix)) / len(cov_matrix)
        return w
    except np.linalg.LinAlgError:
        return np.ones(len(cov_matrix)) / len(cov_matrix)


def inverse_vol_weights(vol_arr):
    """역변동성 비중"""
    inv_vol = 1.0 / np.maximum(vol_arr, 0.01)
    return inv_vol / inv_vol.sum()


def run_portfolio(all_close, weight_method, corr_window):
    """포트폴리오 백테스트"""
    n_symbols = len(all_close)
    n_bars = len(all_close[0])

    cash = TOTAL_CASH
    shares = np.zeros(n_symbols)
    peak_val = TOTAL_CASH; max_dd = 0.0
    n_rebalances = 0

    # Initial allocation
    weights = np.ones(n_symbols) / n_symbols  # start equal

    for i in range(corr_window, n_bars):
        prices = np.array([all_close[j][i] for j in range(n_symbols)])

        # Rebalance check (monthly)
        if i == corr_window or (i - corr_window) % REBALANCE_FREQ == 0:
            # Compute weights
            if weight_method == "equal":
                weights = np.ones(n_symbols) / n_symbols
            elif weight_method == "inverse_vol":
                vols = []
                for j in range(n_symbols):
                    ret = np.diff(np.log(all_close[j][max(0,i-corr_window):i+1]))
                    vols.append(np.std(ret) * np.sqrt(252) if len(ret) > 5 else 1.0)
                weights = inverse_vol_weights(np.array(vols))
            elif weight_method == "min_variance":
                returns = []
                for j in range(n_symbols):
                    r = np.diff(np.log(all_close[j][max(0,i-corr_window):i+1]))
                    returns.append(r[-min(corr_window, len(r)):])
                min_len = min(len(r) for r in returns)
                if min_len < 10:
                    weights = np.ones(n_symbols) / n_symbols
                else:
                    ret_matrix = np.column_stack([r[-min_len:] for r in returns])
                    cov = np.cov(ret_matrix.T)
                    weights = min_variance_weights(cov)

            # Liquidate and reallocate
            total_val = cash + sum(shares[j] * prices[j] for j in range(n_symbols))
            # Sell all
            for j in range(n_symbols):
                if shares[j] > 0:
                    cash += shares[j] * prices[j] * (1 - FEE_RATE)
                    shares[j] = 0
            # Buy with new weights
            for j in range(n_symbols):
                alloc = total_val * weights[j]
                shares[j] = alloc * (1 - FEE_RATE) / prices[j]
                cash -= alloc
            n_rebalances += 1

        # Portfolio value
        val = cash + sum(shares[j] * prices[j] for j in range(n_symbols))
        if val > peak_val: peak_val = val
        dd = (val - peak_val) / peak_val
        if dd < max_dd: max_dd = dd

    # Final
    final_prices = np.array([all_close[j][-1] for j in range(n_symbols)])
    final = cash + sum(shares[j] * final_prices[j] for j in range(n_symbols))
    ret = (final / TOTAL_CASH - 1) * 100
    return n_rebalances, round(ret, 1), round(max_dd * 100, 1)


def run_bh(close):
    shares = TOTAL_CASH * (1 - FEE_RATE) / close[0]
    return round((shares * close[-1] / TOTAL_CASH - 1) * 100, 1)


def main():
    print("=" * 120)
    print("EXP 9: CORRELATION-BASED PORTFOLIO")
    print("=" * 120)

    # Load all data
    dfs = {}
    for sym in SYMBOLS:
        path = f"data/{sym}.parquet"
        if not os.path.exists(path):
            print(f"  SKIP {sym}")
            continue
        dfs[sym] = pd.read_parquet(path).sort_index()

    if len(dfs) < 2:
        print("Not enough symbols")
        return

    # Common index
    common_idx = dfs[SYMBOLS[0]].index
    for sym in SYMBOLS[1:]:
        if sym in dfs:
            common_idx = common_idx.intersection(dfs[sym].index)
    common_idx = common_idx.sort_values()
    print(f"\nCommon dates: {len(common_idx)} bars ({common_idx[0].date()} ~ {common_idx[-1].date()})")

    all_close = []
    for sym in SYMBOLS:
        all_close.append(dfs[sym].loc[common_idx, "close"].values)

    # Individual B&H
    print("\nIndividual B&H:")
    for i, sym in enumerate(SYMBOLS):
        bh = run_bh(all_close[i])
        print(f"  {sym}: {bh:+.1f}%")

    # Correlation matrix
    print("\nFull-period correlation matrix:")
    ret_df = pd.DataFrame({
        sym: pd.Series(np.diff(np.log(all_close[i])))
        for i, sym in enumerate(SYMBOLS)
    })
    print(ret_df.corr().round(3).to_string())

    all_results = []
    methods = ["equal", "inverse_vol", "min_variance"]

    for method in methods:
        for cw in CORR_WINDOWS:
            nreb, ret, mdd = run_portfolio(all_close, method, cw)

            row = {
                "method": method, "corr_window": cw,
                "n_rebalances": nreb,
                "return_pct": ret, "max_dd_pct": mdd,
            }
            # Add individual B&H
            for i, sym in enumerate(SYMBOLS):
                row[f"bh_{sym}"] = run_bh(all_close[i])

            all_results.append(row)

            print(f"\n  {method} (window={cw}): {ret:>+10,.1f}% | MaxDD {mdd}% | {nreb} rebalances")

    res_df = pd.DataFrame(all_results)
    res_df.to_csv("results/exp9_correlation_portfolio.csv", index=False)
    print(f"\nSaved: results/exp9_correlation_portfolio.csv ({len(all_results)} rows)")


if __name__ == "__main__":
    main()
