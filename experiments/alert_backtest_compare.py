"""Alert 전략 비교 백테스트
현재 alert.py 로직 vs 대안 전략들을 동일 조건으로 비교.
"""
import sys
import numpy as np
import pandas as pd
import ta
from pathlib import Path

from backtest.data_loader import load_single
from backtest.metrics import compute_metrics_fast
from config import FeeModel

CAPITAL = 2000
FEE = float(FeeModel.STANDARD)

# alert.py에서 사용하는 종목+파라미터
ALERT_SYMBOLS = {
    "SOXL": {"buy_rsi": 25, "sell_rsi": 60, "rebuy_rsi": 55},
    "TQQQ": {"buy_rsi": 25, "sell_rsi": 65, "rebuy_rsi": 55},
    "SPXL": {"buy_rsi": 30, "sell_rsi": 70, "rebuy_rsi": 55},
    "TNA":  {"buy_rsi": 35, "sell_rsi": 70, "rebuy_rsi": 50},
    "QLD":  {"buy_rsi": 25, "sell_rsi": 70, "rebuy_rsi": 55},
    "QQQ":  {"buy_rsi": 25, "sell_rsi": 75, "rebuy_rsi": 55},
}


def compute_rsi(close, period=14):
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def run_strategy(df, buy_fn, sell_fn, rebuy_fn=None):
    """범용 상태머신 백테스트.
    buy_fn(row, i, df) -> bool
    sell_fn(row, i, df) -> bool
    rebuy_fn(row, i, df) -> bool (None이면 buy_fn 사용)
    """
    close = df["close"].values
    n = len(close)
    equity = np.empty(n)
    cash = CAPITAL
    qty = 0.0
    state = "CASH"  # CASH, HOLDING, WAIT_REBUY
    trades = 0

    for i in range(n):
        row = df.iloc[i]

        if state == "CASH":
            if buy_fn(row, i, df):
                alloc = cash * 0.95
                buy_qty = alloc / (close[i] * (1 + FEE))
                cash -= close[i] * buy_qty * (1 + FEE)
                qty = buy_qty
                state = "HOLDING"
                trades += 1
        elif state == "HOLDING":
            if sell_fn(row, i, df):
                cash += close[i] * qty * (1 - FEE)
                qty = 0.0
                state = "WAIT_REBUY"
                trades += 1
        elif state == "WAIT_REBUY":
            rfn = rebuy_fn if rebuy_fn else buy_fn
            if rfn(row, i, df):
                alloc = cash * 0.95
                buy_qty = alloc / (close[i] * (1 + FEE))
                cash -= close[i] * buy_qty * (1 + FEE)
                qty = buy_qty
                state = "HOLDING"
                trades += 1

        equity[i] = cash + qty * close[i]

    return equity, trades, df.index.values


def add_indicators(df):
    """공통 지표 추가"""
    close = df["close"]
    high = df["high"]
    low = df["low"]

    df = df.copy()
    df["rsi14"] = compute_rsi(close, 14)
    df["rsi7"] = compute_rsi(close, 7)

    bb = ta.volatility.BollingerBands(close, window=20, window_dev=2)
    df["bb_upper"] = bb.bollinger_hband()
    df["bb_lower"] = bb.bollinger_lband()
    df["bb_mid"] = bb.bollinger_mavg()
    df["bb_pctb"] = bb.bollinger_pband()

    df["sma200"] = close.rolling(200).mean()
    df["sma50"] = close.rolling(50).mean()
    df["ema10"] = ta.trend.EMAIndicator(close, 10).ema_indicator()
    df["ema30"] = ta.trend.EMAIndicator(close, 30).ema_indicator()

    atr = ta.volatility.AverageTrueRange(high, low, close, window=14)
    df["atr14"] = atr.average_true_range()

    macd = ta.trend.MACD(close)
    df["macd_diff"] = macd.macd_diff()
    df["macd_signal"] = macd.macd_signal()

    df["volume_ma20"] = df["volume"].rolling(20).mean()

    # Stochastic RSI
    stoch_rsi = ta.momentum.StochRSIIndicator(close, window=14)
    df["stoch_rsi_k"] = stoch_rsi.stochrsi_k()

    return df


# ─── 전략 정의 ───

def strategy_baseline(symbol, cfg, df):
    """현재 alert.py 로직 그대로"""
    buy_rsi = cfg["buy_rsi"]
    sell_rsi = cfg["sell_rsi"]
    rebuy_rsi = cfg["rebuy_rsi"]

    def buy_fn(row, i, df):
        return row["rsi14"] < buy_rsi

    def sell_fn(row, i, df):
        return row["rsi14"] > sell_rsi and row["close"] > row["bb_upper"]

    def rebuy_fn(row, i, df):
        return row["rsi14"] < rebuy_rsi

    return run_strategy(df, buy_fn, sell_fn, rebuy_fn)


def strategy_bb_lower_buy(symbol, cfg, df):
    """가설1: 매수에 BB 하한밴드 조건 추가"""
    buy_rsi = cfg["buy_rsi"]
    sell_rsi = cfg["sell_rsi"]
    rebuy_rsi = cfg["rebuy_rsi"]

    def buy_fn(row, i, df):
        return row["rsi14"] < buy_rsi and row["close"] < row["bb_lower"]

    def sell_fn(row, i, df):
        return row["rsi14"] > sell_rsi and row["close"] > row["bb_upper"]

    def rebuy_fn(row, i, df):
        return row["rsi14"] < rebuy_rsi and row["close"] < row["bb_lower"]

    return run_strategy(df, buy_fn, sell_fn, rebuy_fn)


def strategy_regime_filter(symbol, cfg, df):
    """가설2: SMA200 레짐 필터 (하락장 매수 차단)"""
    buy_rsi = cfg["buy_rsi"]
    sell_rsi = cfg["sell_rsi"]
    rebuy_rsi = cfg["rebuy_rsi"]

    def buy_fn(row, i, df):
        if pd.isna(row["sma200"]):
            return row["rsi14"] < buy_rsi
        return row["rsi14"] < buy_rsi and row["close"] > row["sma200"]

    def sell_fn(row, i, df):
        return row["rsi14"] > sell_rsi and row["close"] > row["bb_upper"]

    def rebuy_fn(row, i, df):
        if pd.isna(row["sma200"]):
            return row["rsi14"] < rebuy_rsi
        return row["rsi14"] < rebuy_rsi and row["close"] > row["sma200"]

    return run_strategy(df, buy_fn, sell_fn, rebuy_fn)


def strategy_trailing_stop(symbol, cfg, df):
    """가설3: 매도를 ATR 트레일링스탑으로 대체"""
    buy_rsi = cfg["buy_rsi"]
    rebuy_rsi = cfg["rebuy_rsi"]
    atr_mult = 2.5

    close = df["close"].values
    atr = df["atr14"].values
    rsi = df["rsi14"].values
    n = len(close)

    equity = np.empty(n)
    cash = CAPITAL
    qty = 0.0
    state = "CASH"
    trades = 0
    trailing_stop = 0.0

    for i in range(n):
        if state == "CASH":
            if not np.isnan(rsi[i]) and rsi[i] < buy_rsi:
                alloc = cash * 0.95
                buy_qty = alloc / (close[i] * (1 + FEE))
                cash -= close[i] * buy_qty * (1 + FEE)
                qty = buy_qty
                state = "HOLDING"
                trades += 1
                trailing_stop = close[i] - atr[i] * atr_mult if not np.isnan(atr[i]) else close[i] * 0.9
        elif state == "HOLDING":
            if not np.isnan(atr[i]):
                new_stop = close[i] - atr[i] * atr_mult
                trailing_stop = max(trailing_stop, new_stop)
            if close[i] < trailing_stop:
                cash += close[i] * qty * (1 - FEE)
                qty = 0.0
                state = "WAIT_REBUY"
                trades += 1
        elif state == "WAIT_REBUY":
            if not np.isnan(rsi[i]) and rsi[i] < rebuy_rsi:
                alloc = cash * 0.95
                buy_qty = alloc / (close[i] * (1 + FEE))
                cash -= close[i] * buy_qty * (1 + FEE)
                qty = buy_qty
                state = "HOLDING"
                trades += 1
                trailing_stop = close[i] - atr[i] * atr_mult if not np.isnan(atr[i]) else close[i] * 0.9

        equity[i] = cash + qty * close[i]

    return equity, trades, df.index.values


def strategy_macd_confirm(symbol, cfg, df):
    """가설4: 매수에 MACD 모멘텀 전환 확인 추가"""
    buy_rsi = cfg["buy_rsi"]
    sell_rsi = cfg["sell_rsi"]
    rebuy_rsi = cfg["rebuy_rsi"]

    def buy_fn(row, i, df):
        return row["rsi14"] < buy_rsi and row["macd_diff"] > 0

    def sell_fn(row, i, df):
        return row["rsi14"] > sell_rsi and row["close"] > row["bb_upper"]

    def rebuy_fn(row, i, df):
        return row["rsi14"] < rebuy_rsi and row["macd_diff"] > 0

    return run_strategy(df, buy_fn, sell_fn, rebuy_fn)


def strategy_wider_rsi(symbol, cfg, df):
    """가설5: RSI 밴드 확장 (더 극단에서만 거래)"""
    buy_rsi = max(15, cfg["buy_rsi"] - 5)
    sell_rsi = min(85, cfg["sell_rsi"] + 5)
    rebuy_rsi = max(40, cfg["rebuy_rsi"] - 5)

    def buy_fn(row, i, df):
        return row["rsi14"] < buy_rsi

    def sell_fn(row, i, df):
        return row["rsi14"] > sell_rsi and row["close"] > row["bb_upper"]

    def rebuy_fn(row, i, df):
        return row["rsi14"] < rebuy_rsi

    return run_strategy(df, buy_fn, sell_fn, rebuy_fn)


def strategy_rsi7_fast(symbol, cfg, df):
    """가설6: RSI(7) 빠른 반응 + 동일 임계값"""
    buy_rsi = cfg["buy_rsi"]
    sell_rsi = cfg["sell_rsi"]
    rebuy_rsi = cfg["rebuy_rsi"]

    def buy_fn(row, i, df):
        return row["rsi7"] < buy_rsi

    def sell_fn(row, i, df):
        return row["rsi7"] > sell_rsi and row["close"] > row["bb_upper"]

    def rebuy_fn(row, i, df):
        return row["rsi7"] < rebuy_rsi

    return run_strategy(df, buy_fn, sell_fn, rebuy_fn)


def strategy_bb_pctb(symbol, cfg, df):
    """가설7: BB %B 기반 진입/청산 (RSI 대체)"""
    def buy_fn(row, i, df):
        return row["bb_pctb"] < 0.0  # 하한밴드 이탈

    def sell_fn(row, i, df):
        return row["bb_pctb"] > 1.0  # 상한밴드 이탈

    def rebuy_fn(row, i, df):
        return row["bb_pctb"] < 0.1

    return run_strategy(df, buy_fn, sell_fn, rebuy_fn)


def strategy_regime_trailing(symbol, cfg, df):
    """가설8: 레짐필터 + 트레일링스탑 복합"""
    buy_rsi = cfg["buy_rsi"]
    rebuy_rsi = cfg["rebuy_rsi"]
    atr_mult = 2.5

    close = df["close"].values
    atr = df["atr14"].values
    rsi = df["rsi14"].values
    sma200 = df["sma200"].values
    n = len(close)

    equity = np.empty(n)
    cash = CAPITAL
    qty = 0.0
    state = "CASH"
    trades = 0
    trailing_stop = 0.0

    for i in range(n):
        bull = not np.isnan(sma200[i]) and close[i] > sma200[i]

        if state == "CASH":
            can_buy = not np.isnan(rsi[i]) and rsi[i] < buy_rsi
            if np.isnan(sma200[i]):
                regime_ok = True
            else:
                regime_ok = bull
            if can_buy and regime_ok:
                alloc = cash * 0.95
                buy_qty = alloc / (close[i] * (1 + FEE))
                cash -= close[i] * buy_qty * (1 + FEE)
                qty = buy_qty
                state = "HOLDING"
                trades += 1
                trailing_stop = close[i] - atr[i] * atr_mult if not np.isnan(atr[i]) else close[i] * 0.9
        elif state == "HOLDING":
            if not np.isnan(atr[i]):
                new_stop = close[i] - atr[i] * atr_mult
                trailing_stop = max(trailing_stop, new_stop)
            if close[i] < trailing_stop or (not np.isnan(sma200[i]) and not bull):
                cash += close[i] * qty * (1 - FEE)
                qty = 0.0
                state = "WAIT_REBUY"
                trades += 1
        elif state == "WAIT_REBUY":
            can_rebuy = not np.isnan(rsi[i]) and rsi[i] < rebuy_rsi
            if np.isnan(sma200[i]):
                regime_ok = True
            else:
                regime_ok = bull
            if can_rebuy and regime_ok:
                alloc = cash * 0.95
                buy_qty = alloc / (close[i] * (1 + FEE))
                cash -= close[i] * buy_qty * (1 + FEE)
                qty = buy_qty
                state = "HOLDING"
                trades += 1
                trailing_stop = close[i] - atr[i] * atr_mult if not np.isnan(atr[i]) else close[i] * 0.9

        equity[i] = cash + qty * close[i]

    return equity, trades, df.index.values


def strategy_stoch_rsi(symbol, cfg, df):
    """가설9: Stochastic RSI로 더 민감한 과매도 감지"""
    def buy_fn(row, i, df):
        if pd.isna(row["stoch_rsi_k"]):
            return False
        return row["stoch_rsi_k"] < 0.1

    def sell_fn(row, i, df):
        if pd.isna(row["stoch_rsi_k"]):
            return False
        return row["stoch_rsi_k"] > 0.9 and row["close"] > row["bb_upper"]

    def rebuy_fn(row, i, df):
        if pd.isna(row["stoch_rsi_k"]):
            return False
        return row["stoch_rsi_k"] < 0.2

    return run_strategy(df, buy_fn, sell_fn, rebuy_fn)


def strategy_sell_bb_only(symbol, cfg, df):
    """가설10: 매도를 BB상단 이탈만으로 (RSI 제거)"""
    buy_rsi = cfg["buy_rsi"]
    rebuy_rsi = cfg["rebuy_rsi"]

    def buy_fn(row, i, df):
        return row["rsi14"] < buy_rsi

    def sell_fn(row, i, df):
        return row["close"] > row["bb_upper"]

    def rebuy_fn(row, i, df):
        return row["rsi14"] < rebuy_rsi

    return run_strategy(df, buy_fn, sell_fn, rebuy_fn)


STRATEGIES = {
    "baseline":         strategy_baseline,
    "bb_lower_buy":     strategy_bb_lower_buy,
    "regime_sma200":    strategy_regime_filter,
    "trailing_stop":    strategy_trailing_stop,
    "macd_confirm":     strategy_macd_confirm,
    "wider_rsi":        strategy_wider_rsi,
    "rsi7_fast":        strategy_rsi7_fast,
    "bb_pctb":          strategy_bb_pctb,
    "regime+trailing":  strategy_regime_trailing,
    "stoch_rsi":        strategy_stoch_rsi,
    "sell_bb_only":     strategy_sell_bb_only,
}


def run_all():
    results = []

    for symbol, cfg in ALERT_SYMBOLS.items():
        try:
            df = load_single(symbol)
        except FileNotFoundError:
            print(f"SKIP {symbol}: no data")
            continue

        df = add_indicators(df)

        for strat_name, strat_fn in STRATEGIES.items():
            equity, trades, dates = strat_fn(symbol, cfg, df)
            metrics = compute_metrics_fast(equity, dates, trades)
            results.append({
                "symbol": symbol,
                "strategy": strat_name,
                "total_return": metrics["total_return"],
                "annualized_return": metrics["annualized_return"],
                "max_drawdown": metrics["max_drawdown"],
                "sharpe": metrics["sharpe_ratio"],
                "calmar": metrics["calmar_ratio"],
                "trades": metrics["total_trades"],
            })

    df_results = pd.DataFrame(results)

    # 종목별 비교
    print("\n" + "="*100)
    print("ALERT STRATEGY COMPARISON BACKTEST")
    print("="*100)

    for symbol in ALERT_SYMBOLS:
        sym_df = df_results[df_results["symbol"] == symbol].copy()
        if sym_df.empty:
            continue

        sym_df = sym_df.sort_values("sharpe", ascending=False)
        print(f"\n{'─'*80}")
        print(f"  {symbol} (buy_rsi={ALERT_SYMBOLS[symbol]['buy_rsi']}, "
              f"sell_rsi={ALERT_SYMBOLS[symbol]['sell_rsi']})")
        print(f"{'─'*80}")
        print(f"{'Strategy':<20} {'Return':>10} {'Ann.Ret':>10} {'MaxDD':>10} "
              f"{'Sharpe':>8} {'Calmar':>8} {'Trades':>7}")

        baseline_sharpe = sym_df[sym_df["strategy"] == "baseline"]["sharpe"].values
        baseline_sharpe = baseline_sharpe[0] if len(baseline_sharpe) > 0 else 0

        for _, row in sym_df.iterrows():
            marker = " ***" if row["strategy"] != "baseline" and row["sharpe"] > baseline_sharpe else ""
            print(f"{row['strategy']:<20} {row['total_return']:>9.1%} {row['annualized_return']:>9.1%} "
                  f"{row['max_drawdown']:>9.1%} {row['sharpe']:>7.3f} {row['calmar']:>7.3f} "
                  f"{row['trades']:>6.0f}{marker}")

    # 전체 평균
    print(f"\n{'='*80}")
    print("  AVERAGE ACROSS ALL SYMBOLS")
    print(f"{'='*80}")
    avg = df_results.groupby("strategy").agg({
        "total_return": "mean",
        "annualized_return": "mean",
        "max_drawdown": "mean",
        "sharpe": "mean",
        "calmar": "mean",
        "trades": "mean",
    }).sort_values("sharpe", ascending=False)

    baseline_avg_sharpe = avg.loc["baseline", "sharpe"] if "baseline" in avg.index else 0

    print(f"{'Strategy':<20} {'Return':>10} {'Ann.Ret':>10} {'MaxDD':>10} "
          f"{'Sharpe':>8} {'Calmar':>8} {'Trades':>7}")
    for strat_name, row in avg.iterrows():
        marker = " ***" if strat_name != "baseline" and row["sharpe"] > baseline_avg_sharpe else ""
        print(f"{strat_name:<20} {row['total_return']:>9.1%} {row['annualized_return']:>9.1%} "
              f"{row['max_drawdown']:>9.1%} {row['sharpe']:>7.3f} {row['calmar']:>7.3f} "
              f"{row['trades']:>6.0f}{marker}")

    # baseline보다 나은 전략 요약
    print(f"\n{'='*80}")
    print("  STRATEGIES BEATING BASELINE (by avg Sharpe)")
    print(f"{'='*80}")
    better = avg[avg["sharpe"] > baseline_avg_sharpe].drop("baseline", errors="ignore")
    if better.empty:
        print("  None — baseline is the best!")
    else:
        for strat_name, row in better.iterrows():
            improvement = (row["sharpe"] - baseline_avg_sharpe) / abs(baseline_avg_sharpe) * 100 if baseline_avg_sharpe != 0 else 0
            print(f"  {strat_name}: Sharpe {row['sharpe']:.3f} (+{improvement:.1f}%), "
                  f"Return {row['total_return']:.1%}, MaxDD {row['max_drawdown']:.1%}, "
                  f"Trades {row['trades']:.0f}")

    # CSV 저장
    csv_path = Path("results/alert_strategy_compare.csv")
    csv_path.parent.mkdir(exist_ok=True)
    df_results.to_csv(csv_path, index=False)
    print(f"\nResults saved to {csv_path}")

    return df_results


if __name__ == "__main__":
    run_all()
