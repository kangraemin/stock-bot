"""
SOXL 매매 시그널 텔레그램 알림
전략: RSI<25 매수 / RSI>60+BB상단 매도 / RSI<55 재매수

Usage: python alert_soxl.py
Cron:  0 6 * * 1-5 cd /Users/ram/programming/vibecoding/stock-bot && .venv/bin/python alert_soxl.py
"""
import os
import json
import urllib.request
import yfinance as yf
import pandas as pd
import numpy as np
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
STATE_FILE = Path(__file__).parent / ".soxl_state.json"


def send_telegram(msg):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": CHAT_ID,
        "text": msg,
        "parse_mode": "Markdown",
    }).encode()
    req = urllib.request.Request(url, data=data)
    urllib.request.urlopen(req)


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


def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"state": "CASH"}  # CASH, HOLDING, WAIT_REBUY


def save_state(state):
    STATE_FILE.write_text(json.dumps(state))


def main():
    # Fetch recent data
    ticker = yf.Ticker("SOXL")
    df = ticker.history(period="1y", interval="1d")
    if len(df) < 50:
        send_telegram("⚠️ SOXL 데이터 부족")
        return

    df["rsi14"] = rsi(df["Close"], 14)
    df["bb_upper"] = bollinger_upper(df["Close"], 20, 2)

    latest = df.iloc[-1]
    prev = df.iloc[-2]
    price = latest["Close"]
    rsi_val = latest["rsi14"]
    bb_up = latest["bb_upper"]
    date = df.index[-1].strftime("%Y-%m-%d")
    change_pct = (price / prev["Close"] - 1) * 100

    state_data = load_state()
    current_state = state_data["state"]

    signal = None
    new_state = current_state

    if current_state == "CASH":
        if rsi_val < 25:
            signal = "BUY"
            new_state = "HOLDING"

    elif current_state == "HOLDING":
        if rsi_val > 60 and price > bb_up:
            signal = "SELL"
            new_state = "WAIT_REBUY"

    elif current_state == "WAIT_REBUY":
        if rsi_val < 55:
            signal = "REBUY"
            new_state = "HOLDING"

    # Build message
    state_emoji = {"CASH": "💵", "HOLDING": "📈", "WAIT_REBUY": "⏳"}
    state_kr = {"CASH": "현금", "HOLDING": "보유중", "WAIT_REBUY": "재매수 대기"}

    if signal:
        signal_emoji = {"BUY": "🟢 매수", "SELL": "🔴 매도", "REBUY": "🟢 재매수"}
        msg = (
            f"{'='*20}\n"
            f"*{signal_emoji[signal]} 시그널!*\n"
            f"{'='*20}\n"
            f"📅 {date}\n"
            f"💰 SOXL ${price:.2f} ({change_pct:+.1f}%)\n"
            f"📊 RSI: {rsi_val:.1f}\n"
            f"📉 BB상단: ${bb_up:.2f}\n"
            f"\n상태: {state_kr[current_state]} → {state_kr[new_state]}"
        )
        save_state({"state": new_state, "last_signal": signal, "last_date": date, "last_price": round(price, 2)})
        send_telegram(msg)
    else:
        # Daily status (no signal)
        msg = (
            f"{state_emoji[current_state]} *SOXL 일간 리포트*\n"
            f"📅 {date}\n"
            f"💰 ${price:.2f} ({change_pct:+.1f}%)\n"
            f"📊 RSI: {rsi_val:.1f}\n"
            f"📉 BB상단: ${bb_up:.2f}\n"
            f"상태: {state_kr[current_state]}\n"
        )
        # Proximity alerts
        if current_state == "CASH" and rsi_val < 35:
            msg += f"\n⚠️ RSI {rsi_val:.1f} → 25 근접 (매수 임박)"
        elif current_state == "HOLDING":
            if rsi_val > 55:
                msg += f"\n⚠️ RSI {rsi_val:.1f} → 60 근접 (매도 주의)"
            if price > bb_up * 0.97:
                msg += f"\n⚠️ BB상단 ${bb_up:.2f} 근접 ({(price/bb_up-1)*100:+.1f}%)"
        elif current_state == "WAIT_REBUY" and rsi_val < 60:
            msg += f"\n⚠️ RSI {rsi_val:.1f} → 55 근접 (재매수 임박)"

        save_state({**state_data, "last_check": date})
        send_telegram(msg)


if __name__ == "__main__":
    main()
