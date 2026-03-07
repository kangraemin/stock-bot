"""
실험 11: Seasonality Analysis
- Part 1: 요일/월/분기별 수익률 통계
- Part 2: 계절성 필터 전략 (Sell in May, Halloween, 약한 달 회피)
"""
import pandas as pd
import numpy as np
import os

TOTAL_CASH = 10000.0
FEE_RATE = 0.0025

SYMBOLS = ["SOXL", "TQQQ", "SPXL", "TNA"]

SEASONAL_STRATEGIES = [
    ("sell_in_may", [11, 12, 1, 2, 3, 4]),          # Nov~Apr (투자), May~Oct (현금)
    ("halloween", [11, 12, 1, 2, 3, 4]),             # same as sell_in_may
    ("avoid_sep", [1,2,3,4,5,6,7,8,10,11,12]),       # 9월만 회피
    ("avoid_aug_sep", [1,2,3,4,5,6,7,10,11,12]),     # 8~9월 회피
    ("q4_only", [10, 11, 12]),                        # Q4만 투자
    ("h2_only", [7, 8, 9, 10, 11, 12]),               # 하반기만
    ("best_3m", None),                                # 종목별 최고 3개월 (동적)
]


def run_seasonal(close, dates, invest_months):
    """특정 월에만 투자하는 전략"""
    n = len(close)
    cash = TOTAL_CASH
    shares = 0.0
    n_buys = 0; n_sells = 0
    peak_val = TOTAL_CASH; max_dd = 0.0
    in_market = False

    for i in range(n):
        price = close[i]
        month = dates[i].month
        should_invest = month in invest_months

        if should_invest and not in_market:
            shares = cash * (1 - FEE_RATE) / price
            cash = 0; n_buys += 1; in_market = True
        elif not should_invest and in_market:
            cash = shares * price * (1 - FEE_RATE)
            shares = 0; n_sells += 1; in_market = False

        val = cash + shares * price
        if val > peak_val: peak_val = val
        dd = (val - peak_val) / peak_val
        if dd < max_dd: max_dd = dd

    final = cash + shares * close[-1]
    ret = (final / TOTAL_CASH - 1) * 100
    return n_buys, n_sells, round(ret, 1), round(max_dd * 100, 1)


def run_bh(close):
    shares = TOTAL_CASH * (1 - FEE_RATE) / close[0]
    return round((shares * close[-1] / TOTAL_CASH - 1) * 100, 1)


def main():
    print("=" * 120)
    print("EXP 11: SEASONALITY ANALYSIS")
    print("=" * 120)

    all_results = []

    for sym in SYMBOLS:
        path = f"data/{sym}.parquet"
        if not os.path.exists(path):
            continue

        df = pd.read_parquet(path).sort_index()
        close = df["close"].values
        dates = df.index
        bh_ret = run_bh(close)

        # Part 1: Monthly statistics
        df["log_ret"] = np.log(df["close"] / df["close"].shift(1))
        df["month"] = df.index.month
        df["weekday"] = df.index.dayofweek  # 0=Mon, 4=Fri

        monthly_stats = df.groupby("month")["log_ret"].agg(["mean", "std", "count"])
        monthly_stats["annualized"] = monthly_stats["mean"] * 252 * 100
        monthly_stats["sharpe"] = monthly_stats["mean"] / monthly_stats["std"] * np.sqrt(252)

        weekday_stats = df.groupby("weekday")["log_ret"].agg(["mean", "std", "count"])
        weekday_names = ["Mon", "Tue", "Wed", "Thu", "Fri"]

        print(f"\n{'='*80}")
        print(f"[{sym}] {len(df)} bars | B&H: {bh_ret:+.1f}%")
        print(f"\n  Monthly Returns (annualized %):")
        month_names = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
        for m in range(1, 13):
            if m in monthly_stats.index:
                row = monthly_stats.loc[m]
                print(f"    {month_names[m-1]}: {row['annualized']:>+8.1f}% (Sharpe {row['sharpe']:+.2f}, n={int(row['count'])})")

        # Find best/worst months
        best_months = monthly_stats.nlargest(3, "mean").index.tolist()
        worst_months = monthly_stats.nsmallest(3, "mean").index.tolist()
        print(f"  Best 3 months:  {[month_names[m-1] for m in best_months]}")
        print(f"  Worst 3 months: {[month_names[m-1] for m in worst_months]}")

        print(f"\n  Weekday Returns:")
        for d in range(5):
            if d in weekday_stats.index:
                row = weekday_stats.loc[d]
                print(f"    {weekday_names[d]}: {row['mean']*100:>+6.3f}% daily (n={int(row['count'])})")

        # Part 2: Seasonal strategies
        print(f"\n  Seasonal Strategies:")
        for name, months in SEASONAL_STRATEGIES:
            if months is None:
                # best_3m: use top 3 months for this symbol
                months = best_months

            nb, ns, ret, mdd = run_seasonal(close, dates, months)

            row_data = {
                "symbol": sym, "strategy": name,
                "invest_months": str(months),
                "n_buys": nb, "n_sells": ns,
                "return_pct": ret, "max_dd_pct": mdd,
                "bh_pct": bh_ret,
                "vs_bh": round(ret - bh_ret, 1),
            }
            all_results.append(row_data)

            print(f"    {name:20s}: {ret:>+10,.1f}% ({nb}B/{ns}S, MaxDD {mdd}%) vs B&H: {ret-bh_ret:+.1f}%")

        # Add monthly stats to results
        for m in range(1, 13):
            if m in monthly_stats.index:
                row = monthly_stats.loc[m]
                all_results.append({
                    "symbol": sym, "strategy": f"stat_month_{m:02d}",
                    "invest_months": str(m),
                    "return_pct": round(row["annualized"], 1),
                    "max_dd_pct": 0,
                    "n_buys": 0, "n_sells": 0,
                    "bh_pct": bh_ret, "vs_bh": 0,
                })

    res_df = pd.DataFrame(all_results)
    res_df.to_csv("results/exp11_seasonality.csv", index=False)
    print(f"\nSaved: results/exp11_seasonality.csv ({len(all_results)} rows)")


if __name__ == "__main__":
    main()
