"""VIX 포지션 스케일링 + 종목군 분리 전략 백테스트

실험 1: VIX Conservative Scaling (SOXL, TQQQ, SPXL, TNA)
실험 2: 종목군별 최적 전략 (Group A/B/C)
"""

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

from backtest.data_loader import load_single
from backtest.metrics import compute_metrics_fast
from config import FeeModel

CAPITAL = 2000
FEE = float(FeeModel.STANDARD)

# ── 기간 설정 ──
PERIODS = {
    "Full": (None, None),
    "Bear2022": ("2022-01-01", "2022-12-31"),
    "Bull2023-24": ("2023-01-01", "2024-12-31"),
}

# ── 실험1 파라미터: (rsi_buy, rsi_sell) ──
EXP1_PARAMS = {
    "SOXL": (25, 60),
    "TQQQ": (25, 65),
    "SPXL": (30, 70),
    "TNA": (35, 70),
}


def load_data(symbol, start=None, end=None):
    df = load_single(symbol, start_date=start, end_date=end)
    return df


def compute_indicators(df):
    close = df["close"]
    rsi = close.ewm(alpha=1 / 14, min_periods=14).mean()
    # manual RSI
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1 / 14, min_periods=14).mean()
    avg_loss = loss.ewm(alpha=1 / 14, min_periods=14).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))

    bb_mid = close.rolling(20).mean()
    bb_std = close.rolling(20).std()
    bb_lower = bb_mid - 2 * bb_std
    bb_upper = bb_mid + 2 * bb_std

    return rsi, bb_lower, bb_upper


def run_rsi_bb_backtest(df, vix_series, rsi_buy, rsi_sell, scale_fn=None):
    """RSI+BB 타이밍 전략. scale_fn이 주어지면 매수 시 포지션 비율 조정."""
    close = df["close"].values
    dates = df.index.values
    rsi, bb_lower, bb_upper = compute_indicators(df)
    rsi_vals = rsi.values
    bb_low = bb_lower.values
    bb_up = bb_upper.values

    cash = CAPITAL
    shares = 0.0
    equity = np.zeros(len(close))
    trades = 0
    in_position = False

    vix_aligned = vix_series.reindex(df.index).ffill().values if vix_series is not None else None

    for i in range(len(close)):
        price = close[i]

        if not in_position:
            if not np.isnan(rsi_vals[i]) and not np.isnan(bb_low[i]):
                if rsi_vals[i] < rsi_buy and price < bb_low[i]:
                    # determine scale
                    alloc = 0.95
                    if scale_fn is not None and vix_aligned is not None and not np.isnan(vix_aligned[i]):
                        alloc = scale_fn(vix_aligned[i])
                    if alloc > 0:
                        invest = cash * alloc
                        cost = invest / (price * (1 + FEE))
                        shares = cost
                        cash -= invest
                        trades += 1
                        in_position = True
        else:
            if not np.isnan(rsi_vals[i]) and not np.isnan(bb_up[i]):
                if rsi_vals[i] > rsi_sell and price > bb_up[i]:
                    proceed = shares * price * (1 - FEE)
                    cash += proceed
                    shares = 0.0
                    trades += 1
                    in_position = False

        equity[i] = cash + shares * price

    metrics = compute_metrics_fast(equity, dates, trades)
    return metrics


def run_buy_and_hold(df):
    """순수 B&H: 첫날 95% 매수 후 보유."""
    close = df["close"].values
    dates = df.index.values
    buy_price = close[0]
    invest = CAPITAL * 0.95
    shares = invest / (buy_price * (1 + FEE))
    remaining_cash = CAPITAL - invest

    equity = remaining_cash + shares * close
    metrics = compute_metrics_fast(equity, dates, 1)
    return metrics


def run_bh_vix_scaling(df, vix_series):
    """B&H + VIX 스케일링: VIX>30 매도, VIX<25 재진입."""
    close = df["close"].values
    dates = df.index.values
    vix_aligned = vix_series.reindex(df.index).ffill().values

    cash = CAPITAL
    shares = 0.0
    equity = np.zeros(len(close))
    trades = 0
    in_position = False

    for i in range(len(close)):
        price = close[i]
        vix_val = vix_aligned[i] if not np.isnan(vix_aligned[i]) else 20.0

        if not in_position:
            if i == 0 or vix_val < 25:
                invest = cash * 0.95
                shares = invest / (price * (1 + FEE))
                cash -= invest
                trades += 1
                in_position = True
        else:
            if vix_val > 30:
                proceed = shares * price * (1 - FEE)
                cash += proceed
                shares = 0.0
                trades += 1
                in_position = False

        equity[i] = cash + shares * price

    metrics = compute_metrics_fast(equity, dates, trades)
    return metrics


def run_buy_only_rsi(df, rsi_buy):
    """Buy-only RSI 타이밍: RSI<threshold에서 매수, 매도 없음."""
    close = df["close"].values
    dates = df.index.values
    rsi, bb_lower, _ = compute_indicators(df)
    rsi_vals = rsi.values
    bb_low = bb_lower.values

    cash = CAPITAL
    shares = 0.0
    equity = np.zeros(len(close))
    trades = 0
    bought = False

    for i in range(len(close)):
        price = close[i]
        if not bought and not np.isnan(rsi_vals[i]) and not np.isnan(bb_low[i]):
            if rsi_vals[i] < rsi_buy and price < bb_low[i]:
                invest = cash * 0.95
                shares = invest / (price * (1 + FEE))
                cash -= invest
                trades += 1
                bought = True
        equity[i] = cash + shares * price

    metrics = compute_metrics_fast(equity, dates, trades)
    return metrics


# ── VIX 스케일링 함수 ──
def vix_level_scale(vix_val):
    if vix_val < 20:
        return 0.95
    elif vix_val < 25:
        return 0.50
    elif vix_val < 30:
        return 0.25
    else:
        return 0.0  # 매수 차단


def make_vix_term_scale(vix3m_series, df_index):
    """VIX/VIX3M 비율 기반 스케일링 클로저 반환."""
    vix3m_aligned = vix3m_series.reindex(df_index).ffill()

    def scale_fn(vix_val):
        return vix_val  # placeholder, actual logic uses ratio

    return vix3m_aligned


def run_rsi_bb_vix_term(df, vix_series, vix3m_series, rsi_buy, rsi_sell):
    """RSI+BB with VIX/VIX3M term structure scaling."""
    close = df["close"].values
    dates = df.index.values
    rsi, bb_lower, bb_upper = compute_indicators(df)
    rsi_vals = rsi.values
    bb_low = bb_lower.values
    bb_up = bb_upper.values

    vix_aligned = vix_series.reindex(df.index).ffill().values
    vix3m_aligned = vix3m_series.reindex(df.index).ffill().values

    cash = CAPITAL
    shares = 0.0
    equity = np.zeros(len(close))
    trades = 0
    in_position = False

    for i in range(len(close)):
        price = close[i]

        if not in_position:
            if not np.isnan(rsi_vals[i]) and not np.isnan(bb_low[i]):
                if rsi_vals[i] < rsi_buy and price < bb_low[i]:
                    vix_v = vix_aligned[i] if not np.isnan(vix_aligned[i]) else 20.0
                    vix3m_v = vix3m_aligned[i] if not np.isnan(vix3m_aligned[i]) else 22.0
                    ratio = vix_v / vix3m_v if vix3m_v > 0 else 1.0

                    if ratio < 0.9:
                        alloc = 0.95
                    elif ratio < 1.0:
                        alloc = 0.70
                    elif ratio < 1.1:
                        alloc = 0.30
                    else:
                        alloc = 0.0

                    if alloc > 0:
                        invest = cash * alloc
                        cost = invest / (price * (1 + FEE))
                        shares = cost
                        cash -= invest
                        trades += 1
                        in_position = True
        else:
            if not np.isnan(rsi_vals[i]) and not np.isnan(bb_up[i]):
                if rsi_vals[i] > rsi_sell and price > bb_up[i]:
                    proceed = shares * price * (1 - FEE)
                    cash += proceed
                    shares = 0.0
                    trades += 1
                    in_position = False

        equity[i] = cash + shares * price

    metrics = compute_metrics_fast(equity, dates, trades)
    return metrics


def fmt_pct(v):
    return f"{v * 100:.1f}%"


def fmt_dollar(v):
    return f"${v:.0f}"


def main():
    # Load VIX data
    vix_full = load_single("^VIX")
    vix3m_full = load_single("^VIX3M")
    vix_close = vix_full["close"]
    vix3m_close = vix3m_full["close"]

    all_results = []

    # ═══════════════════════════════════════════
    # 실험 1: VIX Conservative Scaling
    # ═══════════════════════════════════════════
    print("=" * 90)
    print("실험 1: VIX Conservative Scaling")
    print("=" * 90)

    for period_name, (start, end) in PERIODS.items():
        print(f"\n--- {period_name} ---")
        header = f"{'Symbol':<8} {'Strategy':<16} {'Return':>10} {'Ann.Ret':>10} {'MaxDD':>10} {'Sharpe':>8} {'Trades':>7} {'vs B&H':>10}"
        print(header)
        print("-" * len(header))

        for symbol, (rsi_buy, rsi_sell) in EXP1_PARAMS.items():
            df = load_data(symbol, start, end)
            if df.empty:
                continue

            # B&H baseline
            bh = run_buy_and_hold(df)

            # 1) Baseline: RSI 95%
            baseline = run_rsi_bb_backtest(df, None, rsi_buy, rsi_sell)

            # 2) VIX-Level
            vix_level = run_rsi_bb_backtest(df, vix_close, rsi_buy, rsi_sell, scale_fn=vix_level_scale)

            # 3) VIX-Term
            vix_term = run_rsi_bb_vix_term(df, vix_close, vix3m_close, rsi_buy, rsi_sell)

            for strat_name, m in [("B&H", bh), ("RSI-Baseline", baseline), ("VIX-Level", vix_level), ("VIX-Term", vix_term)]:
                vs_bh = m["total_return"] - bh["total_return"]
                print(f"{symbol:<8} {strat_name:<16} {fmt_pct(m['total_return']):>10} {fmt_pct(m['annualized_return']):>10} {fmt_pct(m['max_drawdown']):>10} {m['sharpe_ratio']:>8.2f} {m['total_trades']:>7} {fmt_pct(vs_bh):>10}")

                all_results.append({
                    "experiment": "Exp1-VIX-Scaling",
                    "period": period_name,
                    "symbol": symbol,
                    "strategy": strat_name,
                    "total_return": m["total_return"],
                    "annualized_return": m["annualized_return"],
                    "max_drawdown": m["max_drawdown"],
                    "sharpe_ratio": m["sharpe_ratio"],
                    "calmar_ratio": m["calmar_ratio"],
                    "trades": m["total_trades"],
                    "vs_bh": vs_bh,
                })

    # ═══════════════════════════════════════════
    # 실험 2: 종목군별 최적 전략
    # ═══════════════════════════════════════════
    print("\n" + "=" * 90)
    print("실험 2: 종목군별 최적 전략")
    print("=" * 90)

    # Group A: 소형주 (TNA, UWM) — RSI 타이밍 vs B&H
    group_a = {"TNA": (35, 70), "UWM": (35, 70)}
    # Group B: 대형/성장 (TQQQ, SPXL, QLD, QQQ) — RSI vs B&H vs B&H+VIX
    group_b = {"TQQQ": (25, 65), "SPXL": (30, 70), "QLD": (30, 65), "QQQ": (30, 70)}
    # Group C: 개별주 (NVDA, GGLL) — B&H vs buy_only RSI
    group_c = {"NVDA": 30, "GGLL": 30}

    for period_name, (start, end) in PERIODS.items():
        # ── Group A ──
        print(f"\n--- {period_name} | Group A (소형주: TNA, UWM) ---")
        header = f"{'Symbol':<8} {'Strategy':<16} {'Return':>10} {'Ann.Ret':>10} {'MaxDD':>10} {'Sharpe':>8} {'Trades':>7} {'vs B&H':>10}"
        print(header)
        print("-" * len(header))

        for symbol, (rsi_buy, rsi_sell) in group_a.items():
            df = load_data(symbol, start, end)
            if df.empty:
                continue
            bh = run_buy_and_hold(df)
            rsi_strat = run_rsi_bb_backtest(df, None, rsi_buy, rsi_sell)

            for strat_name, m in [("B&H", bh), ("RSI-Timing", rsi_strat)]:
                vs_bh = m["total_return"] - bh["total_return"]
                print(f"{symbol:<8} {strat_name:<16} {fmt_pct(m['total_return']):>10} {fmt_pct(m['annualized_return']):>10} {fmt_pct(m['max_drawdown']):>10} {m['sharpe_ratio']:>8.2f} {m['total_trades']:>7} {fmt_pct(vs_bh):>10}")
                all_results.append({
                    "experiment": "Exp2-GroupA",
                    "period": period_name,
                    "symbol": symbol,
                    "strategy": strat_name,
                    "total_return": m["total_return"],
                    "annualized_return": m["annualized_return"],
                    "max_drawdown": m["max_drawdown"],
                    "sharpe_ratio": m["sharpe_ratio"],
                    "calmar_ratio": m["calmar_ratio"],
                    "trades": m["total_trades"],
                    "vs_bh": vs_bh,
                })

        # ── Group B ──
        print(f"\n--- {period_name} | Group B (대형/성장: TQQQ, SPXL, QLD, QQQ) ---")
        print(header)
        print("-" * len(header))

        for symbol, (rsi_buy, rsi_sell) in group_b.items():
            df = load_data(symbol, start, end)
            if df.empty:
                continue
            bh = run_buy_and_hold(df)
            rsi_strat = run_rsi_bb_backtest(df, None, rsi_buy, rsi_sell)
            bh_vix = run_bh_vix_scaling(df, vix_close)

            for strat_name, m in [("B&H", bh), ("RSI-Timing", rsi_strat), ("B&H+VIX", bh_vix)]:
                vs_bh = m["total_return"] - bh["total_return"]
                print(f"{symbol:<8} {strat_name:<16} {fmt_pct(m['total_return']):>10} {fmt_pct(m['annualized_return']):>10} {fmt_pct(m['max_drawdown']):>10} {m['sharpe_ratio']:>8.2f} {m['total_trades']:>7} {fmt_pct(vs_bh):>10}")
                all_results.append({
                    "experiment": "Exp2-GroupB",
                    "period": period_name,
                    "symbol": symbol,
                    "strategy": strat_name,
                    "total_return": m["total_return"],
                    "annualized_return": m["annualized_return"],
                    "max_drawdown": m["max_drawdown"],
                    "sharpe_ratio": m["sharpe_ratio"],
                    "calmar_ratio": m["calmar_ratio"],
                    "trades": m["total_trades"],
                    "vs_bh": vs_bh,
                })

        # ── Group C ──
        print(f"\n--- {period_name} | Group C (개별주: NVDA, GGLL) ---")
        print(header)
        print("-" * len(header))

        for symbol, rsi_buy in group_c.items():
            df = load_data(symbol, start, end)
            if df.empty:
                continue
            bh = run_buy_and_hold(df)
            buy_only = run_buy_only_rsi(df, rsi_buy)

            for strat_name, m in [("B&H", bh), ("BuyOnly-RSI", buy_only)]:
                vs_bh = m["total_return"] - bh["total_return"]
                print(f"{symbol:<8} {strat_name:<16} {fmt_pct(m['total_return']):>10} {fmt_pct(m['annualized_return']):>10} {fmt_pct(m['max_drawdown']):>10} {m['sharpe_ratio']:>8.2f} {m['total_trades']:>7} {fmt_pct(vs_bh):>10}")
                all_results.append({
                    "experiment": "Exp2-GroupC",
                    "period": period_name,
                    "symbol": symbol,
                    "strategy": strat_name,
                    "total_return": m["total_return"],
                    "annualized_return": m["annualized_return"],
                    "max_drawdown": m["max_drawdown"],
                    "sharpe_ratio": m["sharpe_ratio"],
                    "calmar_ratio": m["calmar_ratio"],
                    "trades": m["total_trades"],
                    "vs_bh": vs_bh,
                })

    # ── CSV 저장 ──
    results_dir = pathlib.Path(__file__).resolve().parent.parent / "results"
    results_dir.mkdir(exist_ok=True)
    results_df = pd.DataFrame(all_results)
    csv_path = results_dir / "analyst_vix_group_results.csv"
    results_df.to_csv(csv_path, index=False)
    print(f"\n결과 저장: {csv_path}")

    # ── 핵심 결론 ──
    print("\n" + "=" * 90)
    print("핵심 결론")
    print("=" * 90)

    # Full period 기준 분석
    full = results_df[results_df["period"] == "Full"]

    print("\n[실험1] VIX 스케일링 효과 (Full period):")
    for sym in EXP1_PARAMS:
        sym_data = full[(full["symbol"] == sym) & (full["experiment"] == "Exp1-VIX-Scaling")]
        if sym_data.empty:
            continue
        best = sym_data.loc[sym_data["sharpe_ratio"].idxmax()]
        print(f"  {sym}: 최적 전략 = {best['strategy']}, Sharpe={best['sharpe_ratio']:.2f}, Return={best['total_return']*100:.1f}%, MaxDD={best['max_drawdown']*100:.1f}%")

    print("\n[실험2] 종목군별 판정 (Full period):")
    for exp, label in [("Exp2-GroupA", "Group A 소형주"), ("Exp2-GroupB", "Group B 대형/성장"), ("Exp2-GroupC", "Group C 개별주")]:
        exp_data = full[full["experiment"] == exp]
        if exp_data.empty:
            continue
        print(f"\n  {label}:")
        for sym in exp_data["symbol"].unique():
            sym_data = exp_data[exp_data["symbol"] == sym]
            best = sym_data.loc[sym_data["sharpe_ratio"].idxmax()]
            print(f"    {sym}: 최적 = {best['strategy']}, Sharpe={best['sharpe_ratio']:.2f}, Return={best['total_return']*100:.1f}%, Trades={best['trades']}")


if __name__ == "__main__":
    main()
