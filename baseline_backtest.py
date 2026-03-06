"""SOXL Baseline Backtests: Buy & Hold, Weekly DCA, Monthly DCA"""
import pandas as pd
import numpy as np

FEE_RATE = 0.0025  # 0.25% one-way buy fee

def load_daily():
    df = pd.read_parquet("data/SOXL.parquet")
    df.index = pd.to_datetime(df.index)
    df = df.sort_index().reset_index()
    df = df.rename(columns={"Date": "date"})
    return df

def load_hourly():
    df = pd.read_parquet("data/SOXL_1h.parquet")
    df.index = pd.to_datetime(df.index)
    df = df.sort_index().reset_index()
    df = df.rename(columns={"Datetime": "date"})
    # strip timezone for comparison
    df["date"] = df["date"].dt.tz_localize(None)
    return df

def compute_metrics(prices: pd.Series, annualize_factor: float):
    cummax = prices.cummax()
    dd = (prices - cummax) / cummax
    max_dd = dd.min()
    returns = prices.pct_change().dropna()
    if returns.std() == 0:
        sharpe = 0.0
    else:
        sharpe = returns.mean() / returns.std() * np.sqrt(annualize_factor)
    return max_dd, sharpe

def buy_and_hold(df, capital=2000.0, ann_factor=252):
    price = df.iloc[0]["close"]
    fee = capital * FEE_RATE
    shares = (capital - fee) / price

    portfolio = shares * df["close"]
    final = portfolio.iloc[-1]
    total_return = (final - capital) / capital * 100
    max_dd, sharpe = compute_metrics(portfolio, ann_factor)

    return {
        "Strategy": "Buy & Hold",
        "Final Value": f"${final:,.2f}",
        "Total Return": f"{total_return:,.2f}%",
        "MaxDD": f"{max_dd*100:.2f}%",
        "Sharpe": f"{sharpe:.4f}",
        "Avg Cost": f"${price:.2f}",
        "Buy Count": 1,
    }

def weekly_dca(df, capital=2000.0, ann_factor=252):
    df = df.copy()
    df["week"] = df["date"].dt.isocalendar().week.astype(int)
    df["year"] = df["date"].dt.year

    buy_days_idx = df.groupby(["year", "week"]).apply(lambda g: g.index[0])
    buy_set = set(buy_days_idx.values)
    n_weeks = len(buy_set)
    amount_per_week = capital / n_weeks

    costs = []
    for idx in sorted(buy_set):
        row = df.loc[idx]
        fee = amount_per_week * FEE_RATE
        shares_bought = (amount_per_week - fee) / row["close"]
        costs.append((shares_bought, row["close"]))

    # Build portfolio series
    shares_cum = 0.0
    buy_idx = 0
    sorted_buys = sorted(buy_set)
    daily_values = []
    for i, row in df.iterrows():
        if buy_idx < len(sorted_buys) and i == sorted_buys[buy_idx]:
            shares_cum += costs[buy_idx][0]
            buy_idx += 1
        daily_values.append(shares_cum * row["close"])

    portfolio = pd.Series(daily_values)
    first_nonzero = (portfolio > 0).idxmax()
    portfolio = portfolio.iloc[first_nonzero:]

    total_shares = sum(s for s, _ in costs)
    final = total_shares * df.iloc[-1]["close"]
    total_return = (final - capital) / capital * 100
    avg_cost = sum(s * p for s, p in costs) / total_shares
    max_dd, sharpe = compute_metrics(portfolio, ann_factor)

    return {
        "Strategy": "Weekly DCA",
        "Final Value": f"${final:,.2f}",
        "Total Return": f"{total_return:,.2f}%",
        "MaxDD": f"{max_dd*100:.2f}%",
        "Sharpe": f"{sharpe:.4f}",
        "Avg Cost": f"${avg_cost:.2f}",
        "Buy Count": n_weeks,
    }

def monthly_dca(df, capital=2000.0, ann_factor=252):
    df = df.copy()
    df["month"] = df["date"].dt.month
    df["year"] = df["date"].dt.year

    buy_days_idx = df.groupby(["year", "month"]).apply(lambda g: g.index[0])
    buy_set = set(buy_days_idx.values)
    n_months = len(buy_set)
    amount_per_month = capital / n_months

    costs = []
    for idx in sorted(buy_set):
        row = df.loc[idx]
        fee = amount_per_month * FEE_RATE
        shares_bought = (amount_per_month - fee) / row["close"]
        costs.append((shares_bought, row["close"]))

    shares_cum = 0.0
    buy_idx = 0
    sorted_buys = sorted(buy_set)
    daily_values = []
    for i, row in df.iterrows():
        if buy_idx < len(sorted_buys) and i == sorted_buys[buy_idx]:
            shares_cum += costs[buy_idx][0]
            buy_idx += 1
        daily_values.append(shares_cum * row["close"])

    portfolio = pd.Series(daily_values)
    first_nonzero = (portfolio > 0).idxmax()
    portfolio = portfolio.iloc[first_nonzero:]

    total_shares = sum(s for s, _ in costs)
    final = total_shares * df.iloc[-1]["close"]
    total_return = (final - capital) / capital * 100
    avg_cost = sum(s * p for s, p in costs) / total_shares
    max_dd, sharpe = compute_metrics(portfolio, ann_factor)

    return {
        "Strategy": "Monthly DCA",
        "Final Value": f"${final:,.2f}",
        "Total Return": f"{total_return:,.2f}%",
        "MaxDD": f"{max_dd*100:.2f}%",
        "Sharpe": f"{sharpe:.4f}",
        "Avg Cost": f"${avg_cost:.2f}",
        "Buy Count": n_months,
    }

def run_all():
    daily = load_daily()
    hourly = load_hourly()

    cutoff = pd.Timestamp("2023-01-01")
    daily_recent = daily[daily["date"] >= cutoff].reset_index(drop=True)

    print(f"Daily data: {daily['date'].min().date()} ~ {daily['date'].max().date()} ({len(daily)} rows)")
    print(f"Daily recent: {daily_recent['date'].min().date()} ~ {daily_recent['date'].max().date()} ({len(daily_recent)} rows)")
    print(f"Hourly data: {hourly['date'].min().date()} ~ {hourly['date'].max().date()} ({len(hourly)} rows)")
    print()

    datasets = [
        ("Daily Full (2010~2026)", daily, 252),
        ("Daily Recent (2023~2026)", daily_recent, 252),
        ("Hourly Full", hourly, 1638),
    ]

    for name, df, ann in datasets:
        print(f"=== {name} ===")
        results = [
            buy_and_hold(df, ann_factor=ann),
            weekly_dca(df, ann_factor=ann),
            monthly_dca(df, ann_factor=ann),
        ]
        header = f"{'Strategy':<15} {'Final Value':>14} {'Total Return':>14} {'MaxDD':>10} {'Sharpe':>10} {'Avg Cost':>12} {'Buys':>6}"
        print(header)
        print("-" * len(header))
        for r in results:
            print(f"{r['Strategy']:<15} {r['Final Value']:>14} {r['Total Return']:>14} {r['MaxDD']:>10} {r['Sharpe']:>10} {r['Avg Cost']:>12} {r['Buy Count']:>6}")
        print()

if __name__ == "__main__":
    run_all()
