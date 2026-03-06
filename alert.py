"""
멀티 종목 매매 시그널 텔레그램 알림
- 레버리지 ETF: RSI 기반 매수/매도/재매수 시그널
- DCA 가중치: RSI<45이면 부스트 매수 알림
- 매일 오전 6시(KST) cron 실행

Usage: python alert.py
Cron:  0 21 * * 0-4 cd /home/ubuntu/stock-bot && venv/bin/python alert.py
"""
import os
import json
import urllib.request
import urllib.parse
import yfinance as yf
import pandas as pd
import numpy as np
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
STATE_DIR = Path(__file__).parent / ".states"
STATE_DIR.mkdir(exist_ok=True)

# 종목별 설정 (그리드 서치 최적값 기반)
SYMBOLS = {
    "SOXL": {"group": "3x 반도체", "buy_rsi": 25, "sell_rsi": 60, "rebuy_rsi": 55,
             "desc": "반도체 3배 레버리지"},
    "TQQQ": {"group": "3x 나스닥", "buy_rsi": 25, "sell_rsi": 65, "rebuy_rsi": 55,
             "desc": "나스닥100 3배 레버리지"},
    "SPXL": {"group": "3x S&P500", "buy_rsi": 30, "sell_rsi": 70, "rebuy_rsi": 55,
             "desc": "S&P500 3배 레버리지"},
    "TNA":  {"group": "3x 소형주", "buy_rsi": 35, "sell_rsi": 70, "rebuy_rsi": 50,
             "desc": "러셀2000 3배 레버리지", "macro_filter": "copper"},
    "QLD":  {"group": "2x 나스닥", "buy_rsi": 25, "sell_rsi": 70, "rebuy_rsi": 55,
             "desc": "나스닥100 2배 레버리지"},
    "UWM":  {"group": "2x 소형주", "buy_rsi": 25, "sell_rsi": 70, "rebuy_rsi": 50,
             "desc": "러셀2000 2배 레버리지", "macro_filter": "copper"},
    "QQQ":  {"group": "나스닥100", "buy_rsi": 25, "sell_rsi": 75, "rebuy_rsi": 55,
             "desc": "나스닥100 인덱스"},
}

DCA_BOOST_RSI = 45
COPPER_SMA_PERIOD = 50  # 구리 SMA 기간 (백테스트 최적)
ATR_PERIOD = 14
ATR_AVG_WINDOW = 60  # ATR 평균 비교 기간


def get_copper_trend():
    """구리(HG=F) SMA50 대비 위치 → 'up' or 'down'"""
    try:
        ticker = yf.Ticker("HG=F")
        df = ticker.history(period="6mo", interval="1d")
        if len(df) < COPPER_SMA_PERIOD:
            return None, None, None
        close = df["Close"].iloc[-1]
        sma = df["Close"].rolling(COPPER_SMA_PERIOD).mean().iloc[-1]
        trend = "up" if close > sma else "down"
        return trend, close, sma
    except Exception:
        return None, None, None


def get_vix_term():
    """VIX/VIX3M ratio → contango/backwardation 판별"""
    try:
        vix = yf.Ticker("^VIX").history(period="5d", interval="1d")
        vix3m = yf.Ticker("^VIX3M").history(period="5d", interval="1d")
        if len(vix) < 1 or len(vix3m) < 1:
            return None, None, None
        v = vix["Close"].iloc[-1]
        v3m = vix3m["Close"].iloc[-1]
        ratio = v / v3m
        if ratio > 1.05:
            status = "backwardation"
        elif ratio < 0.95:
            status = "contango"
        else:
            status = "neutral"
        return status, round(ratio, 3), round(v, 1)
    except Exception:
        return None, None, None


def get_atr_ratio(symbol):
    """현재 ATR vs 평균 ATR 비교 → 변동성 수준"""
    try:
        df = yf.Ticker(symbol).history(period="6mo", interval="1d")
        if len(df) < ATR_AVG_WINDOW + ATR_PERIOD:
            return None, None
        tr = np.maximum(
            df["High"] - df["Low"],
            np.maximum(
                abs(df["High"] - df["Close"].shift(1)),
                abs(df["Low"] - df["Close"].shift(1)),
            ),
        )
        atr_series = tr.rolling(ATR_PERIOD).mean()
        current_atr = atr_series.iloc[-1]
        avg_atr = atr_series.iloc[-ATR_AVG_WINDOW:].mean()
        ratio = current_atr / avg_atr if avg_atr > 0 else 1.0
        return round(ratio, 2), round(current_atr, 2)
    except Exception:
        return None, None


def send_telegram(msg):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": CHAT_ID,
        "text": msg,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }).encode()
    try:
        req = urllib.request.Request(url, data=data)
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        print(f"Telegram error: {e}")


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


def load_state(symbol):
    f = STATE_DIR / f"{symbol}.json"
    if f.exists():
        return json.loads(f.read_text())
    return {"state": "CASH"}


def save_state(symbol, state):
    f = STATE_DIR / f"{symbol}.json"
    f.write_text(json.dumps(state))


def check_symbol(symbol, config, copper_trend=None):
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period="3mo", interval="1d")
        if len(df) < 30:
            return None, f"{symbol} 데이터 부족"

        df["rsi14"] = rsi(df["Close"], 14)
        df["bb_upper"] = bollinger_upper(df["Close"], 20, 2)

        latest = df.iloc[-1]
        prev = df.iloc[-2]
        price = latest["Close"]
        rsi_val = latest["rsi14"]
        bb_up = latest["bb_upper"]
        change_pct = (price / prev["Close"] - 1) * 100
        date = df.index[-1].strftime("%Y-%m-%d")

        state_data = load_state(symbol)
        current_state = state_data["state"]

        buy_rsi = config["buy_rsi"]
        sell_rsi = config["sell_rsi"]
        rebuy_rsi = config["rebuy_rsi"]

        # 구리 필터: copper_trend가 "down"이면 매수/재매수 차단
        has_copper_filter = config.get("macro_filter") == "copper"
        copper_blocked = has_copper_filter and copper_trend == "down"

        signal = None
        new_state = current_state
        reason = ""

        if current_state == "CASH":
            if rsi_val < buy_rsi:
                if copper_blocked:
                    reason = f"RSI {rsi_val:.0f} < {buy_rsi} 매수 조건이지만 구리 하락 중 → 매수 보류"
                else:
                    signal = "BUY"
                    new_state = "HOLDING"
                    reason = f"RSI {rsi_val:.0f} < {buy_rsi} (과매도 진입)"
        elif current_state == "HOLDING":
            if rsi_val > sell_rsi and price > bb_up:
                signal = "SELL"
                new_state = "WAIT_REBUY"
                reason = f"RSI {rsi_val:.0f} > {sell_rsi} + BB상단(${bb_up:.2f}) 돌파"
        elif current_state == "WAIT_REBUY":
            if rsi_val < rebuy_rsi:
                if copper_blocked:
                    reason = f"RSI {rsi_val:.0f} < {rebuy_rsi} 재매수 조건이지만 구리 하락 중 → 재매수 보류"
                else:
                    signal = "REBUY"
                    new_state = "HOLDING"
                    reason = f"RSI {rsi_val:.0f} < {rebuy_rsi} (과매도 재진입)"

        # Proximity warnings
        warnings = []
        if current_state == "CASH" and rsi_val < buy_rsi + 10:
            warnings.append(f"매수 임박: RSI {rsi_val:.0f} (목표 {buy_rsi})")
        elif current_state == "HOLDING":
            if rsi_val > sell_rsi - 5:
                warnings.append(f"매도 근접: RSI {rsi_val:.0f} (목표 {sell_rsi})")
            if price > bb_up * 0.97:
                warnings.append(f"BB상단 근접: ${bb_up:.1f} ({(price/bb_up-1)*100:+.1f}%)")
        elif current_state == "WAIT_REBUY" and rsi_val < rebuy_rsi + 5:
            warnings.append(f"재매수 임박: RSI {rsi_val:.0f} (목표 {rebuy_rsi})")

        dca_boost = rsi_val < DCA_BOOST_RSI
        atr_ratio, atr_val = get_atr_ratio(symbol)

        if signal:
            save_state(symbol, {"state": new_state, "last_signal": signal,
                                "last_date": date, "last_price": round(price, 2)})
        else:
            save_state(symbol, {**state_data, "last_check": date})

        return {
            "symbol": symbol,
            "desc": config["desc"],
            "group": config["group"],
            "price": price,
            "change_pct": change_pct,
            "rsi": rsi_val,
            "bb_upper": bb_up,
            "state": current_state,
            "new_state": new_state,
            "signal": signal,
            "reason": reason,
            "warnings": warnings,
            "dca_boost": dca_boost,
            "date": date,
            "config": config,
            "copper_blocked": copper_blocked if has_copper_filter else None,
            "atr_ratio": atr_ratio,
            "atr_val": atr_val,
        }, None

    except Exception as e:
        return None, f"{symbol}: {e}"


def main():
    results = []
    errors = []

    # 매크로 데이터
    copper_trend, copper_price, copper_sma = get_copper_trend()
    vix_status, vix_ratio, vix_val = get_vix_term()

    for symbol, config in SYMBOLS.items():
        ct = copper_trend if config.get("macro_filter") == "copper" else None
        result, error = check_symbol(symbol, config, copper_trend=ct)
        if error:
            errors.append(error)
        if result:
            results.append(result)

    if not results:
        send_telegram("stock-bot: 모든 종목 데이터 실패")
        return

    date = results[0]["date"]
    state_kr = {"CASH": "현금 보유", "HOLDING": "주식 보유중", "WAIT_REBUY": "매도 후 재매수 대기"}
    state_short = {"CASH": "현금", "HOLDING": "보유", "WAIT_REBUY": "대기"}

    signals = [r for r in results if r["signal"]]
    msgs = []

    # ── Header ──
    msgs.append(f"📊 Stock Bot ({date})")
    msgs.append("")

    # ── SIGNALS ──
    if signals:
        for r in signals:
            emoji = {"BUY": "🟢", "SELL": "🔴", "REBUY": "🟢"}
            action = {"BUY": "매수", "SELL": "매도", "REBUY": "재매수"}
            msgs.append(f"{emoji[r['signal']]} {r['symbol']} {action[r['signal']]} 시그널!")
            msgs.append(f"종목: {r['desc']}")
            msgs.append(f"가격: ${r['price']:.2f} ({r['change_pct']:+.1f}%)")
            msgs.append(f"RSI: {r['rsi']:.0f}")
            msgs.append(f"사유: {r['reason']}")
            msgs.append(f"상태: {state_kr[r['state']]} → {state_kr[r['new_state']]}")
            # 포지션 사이징 조언 (매수/재매수 시)
            if r["signal"] in ("BUY", "REBUY"):
                sizing = _position_advice(r, vix_status)
                if sizing:
                    msgs.append(f"💡 {sizing}")
            msgs.append("")

    # ── 종목별 현황 ──
    msgs.append("📋 종목별 현황")
    msgs.append("")

    for r in results:
        st = state_short[r["new_state"] if r["signal"] else r["state"]]
        rsi_bar = _rsi_bar(r["rsi"])
        c = r["config"]

        msgs.append(f"*{r['symbol']}* - {r['desc']}")
        msgs.append(f"가격: ${r['price']:.2f} ({r['change_pct']:+.1f}%)")
        msgs.append(f"RSI: {r['rsi']:.0f} {rsi_bar}")

        # 지금 뭘 해야 하는지
        action = _what_to_do(r)
        msgs.append(f"→ {action}")

        msgs.append("")

    # ── Errors ──
    if errors:
        for e in errors:
            msgs.append(f"⚠️ {e}")
        msgs.append("")

    # ── 매크로 ──
    macro_lines = []
    if copper_trend:
        trend_emoji = "📈" if copper_trend == "up" else "📉"
        macro_lines.append(f"구리 {trend_emoji} ${copper_price:.2f} (SMA50 ${copper_sma:.2f})")
        if copper_trend == "down":
            macro_lines.append("→ 구리 하락 중: TNA/UWM 매수 보류 권장")
    if vix_status:
        vix_emoji = {"contango": "🟢", "neutral": "🟡", "backwardation": "🔴"}
        vix_label = {"contango": "콘탱고(정상)", "neutral": "중립", "backwardation": "백워데이션(공포)"}
        macro_lines.append(f"VIX {vix_emoji[vix_status]} {vix_label[vix_status]} (VIX/VIX3M={vix_ratio}, VIX={vix_val})")
        if vix_status == "backwardation":
            macro_lines.append("→ VIX 백워데이션: 포지션 축소 or 신규 진입 주의")
    if macro_lines:
        msgs.append("🔧 매크로")
        msgs.extend(macro_lines)
        msgs.append("")

    # ── 용어 설명 ──
    msgs.append("ℹ️ 용어")
    msgs.append("RSI: 과매도(<30)/과매수(>70) 지표")
    msgs.append("BB: 볼린저밴드 (가격 변동 범위)")
    msgs.append("DCA: 매월 정기 분할 매수")
    msgs.append("VIX Term: 콘탱고=안전, 백워데이션=공포")
    msgs.append("ATR: 변동성 지표 (높으면 포지션 축소)")


    send_telegram("\n".join(msgs))


def _what_to_do(r):
    """현재 상태 + RSI 기반으로 행동 지침 생성"""
    rv = r["rsi"]
    state = r["new_state"] if r["signal"] else r["state"]
    c = r["config"]
    copper_blocked = r.get("copper_blocked")

    if r["signal"] == "BUY":
        return "지금 매수 타이밍!"
    elif r["signal"] == "SELL":
        return "지금 매도 타이밍!"
    elif r["signal"] == "REBUY":
        return "지금 재매수 타이밍!"

    if state == "CASH":
        gap = rv - c["buy_rsi"]
        if copper_blocked and gap < 10:
            return f"매수 조건 근접 but 구리↓ 매수 보류 (RSI {gap:.0f} 남음)"
        elif gap < 10:
            return f"매수 대기 중 (RSI {gap:.0f} 더 떨어지면 매수)"
        else:
            return "매수 대기 중 (아직 멀음, 관망)"

    elif state == "HOLDING":
        sell_gap = c["sell_rsi"] - rv
        bb_close = r["price"] > r["bb_upper"] * 0.97
        if sell_gap < 5 and bb_close:
            return f"매도 임박! (RSI {sell_gap:.0f} 남음 + BB상단 근접)"
        elif sell_gap < 5:
            return f"매도 근접 (RSI {sell_gap:.0f} 남음, BB상단 대기)"
        elif r.get("dca_boost"):
            atr_r = r.get("atr_ratio")
            if atr_r and atr_r > 1.3:
                return f"보유 유지 + DCA 추가매수 구간 (변동성↑ 소량 추천)"
            return "보유 유지 + DCA 추가매수 추천 구간"
        else:
            return "보유 유지 (매도 조건 아님)"

    elif state == "WAIT_REBUY":
        gap = rv - c["rebuy_rsi"]
        if copper_blocked and gap < 5:
            return f"재매수 조건 근접 but 구리↓ 재매수 보류 (RSI {gap:.0f} 남음)"
        elif gap < 5:
            return f"재매수 임박! (RSI {gap:.0f} 더 떨어지면 재매수)"
        else:
            return f"재매수 대기 중 (RSI {gap:.0f} 더 떨어져야 함)"

    return "관망"


def _position_advice(r, vix_status):
    """ATR 변동성 + VIX term 기반 포지션 사이징 조언"""
    parts = []
    atr_ratio = r.get("atr_ratio")
    if atr_ratio is not None:
        if atr_ratio > 1.5:
            parts.append(f"변동성 매우 높음(ATR x{atr_ratio}) → 50% 포지션 권장")
        elif atr_ratio > 1.2:
            parts.append(f"변동성 높음(ATR x{atr_ratio}) → 70% 포지션 권장")
        else:
            parts.append("변동성 정상 → 풀 포지션 가능")
    if vix_status == "backwardation":
        parts.append("VIX 백워데이션 → 보수적 진입")
    if not parts:
        return None
    return " / ".join(parts)


def _rsi_bar(rsi_val):
    """RSI를 시각적 바로 표현"""
    if rsi_val < 25:
        return "▁▁ 극과매도"
    elif rsi_val < 35:
        return "▂▂ 과매도"
    elif rsi_val < 45:
        return "▃▃ 약세"
    elif rsi_val < 55:
        return "▅▅ 중립"
    elif rsi_val < 65:
        return "▆▆ 강세"
    elif rsi_val < 75:
        return "▇▇ 과매수"
    else:
        return "██ 극과매수"


if __name__ == "__main__":
    main()
