"""
텔레그램 봇 리스너 — /status 명령어로 실시간 종목 조회
Long polling 방식, 추가 의존성 없음 (urllib 사용)

Usage: python bot_listener.py
Systemd: stock-bot-listener.service
"""
import os
import json
import time
import urllib.request
import urllib.parse
import traceback

from dotenv import load_dotenv

import alert

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ALLOWED_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
POLL_TIMEOUT = 30


def get_updates(offset=None):
    """Telegram getUpdates (long polling)"""
    params = {"timeout": POLL_TIMEOUT}
    if offset is not None:
        params["offset"] = offset
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates?" + urllib.parse.urlencode(params)
    try:
        req = urllib.request.Request(url)
        resp = urllib.request.urlopen(req, timeout=POLL_TIMEOUT + 10)
        data = json.loads(resp.read().decode())
        if data.get("ok"):
            return data.get("result", [])
    except Exception:
        time.sleep(5)
    return []


def send_reply(chat_id, text):
    """텔레그램 메시지 전송"""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }).encode()
    try:
        req = urllib.request.Request(url, data=data)
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        print(f"Send error: {e}")


def build_status(symbol=None):
    """/status 응답 생성"""
    if symbol and symbol not in alert.SYMBOLS:
        available = ", ".join(alert.SYMBOLS.keys())
        return f"알 수 없는 종목: {symbol}\n사용 가능: {available}"

    copper_trend, copper_price, copper_sma = alert.get_copper_trend()
    vix_status, vix_ratio, vix_val = alert.get_vix_term()

    state_short = {"CASH": "현금", "HOLDING": "보유", "WAIT_REBUY": "대기"}

    if symbol:
        # 단일 종목 상세
        config = alert.SYMBOLS[symbol]
        ct = copper_trend if config.get("macro_filter") == "copper" else None
        result, error = alert.check_symbol(symbol, config, copper_trend=ct)
        if error:
            return f"오류: {error}"

        r = result
        rsi_bar = alert._rsi_bar(r["rsi"])
        action = alert._what_to_do(r)
        st = state_short.get(r["new_state"] if r["signal"] else r["state"], "?")

        lines = [
            f"*{symbol}* — {r['desc']}",
            f"가격: ${r['price']:.2f} ({r['change_pct']:+.1f}%)",
            f"RSI: {r['rsi']:.0f} {rsi_bar}",
            f"상태: {st}",
            f"→ {action}",
        ]

        if r["signal"]:
            sig_name = {"BUY": "매수", "SELL": "매도", "REBUY": "재매수", "BUY_TIMING": "매수 적기"}
            lines.append(f"시그널: {sig_name.get(r['signal'], r['signal'])}!")

        if r.get("warnings"):
            for w in r["warnings"]:
                lines.append(f"⚠️ {w}")

        if r["signal"] in ("BUY", "REBUY"):
            sizing = alert._position_advice(r, vix_status)
            if sizing:
                lines.append(f"💡 {sizing}")

        # 매크로 정보
        if config.get("macro_filter") == "copper" and copper_trend:
            trend_emoji = "📈" if copper_trend == "up" else "📉"
            lines.append(f"구리 {trend_emoji} ${copper_price:.2f} (SMA50 ${copper_sma:.2f})")

        if vix_status:
            vix_emoji = {"contango": "🟢", "neutral": "🟡", "backwardation": "🔴"}
            vix_label = {"contango": "콘탱고", "neutral": "중립", "backwardation": "백워데이션"}
            lines.append(f"VIX {vix_emoji[vix_status]} {vix_label[vix_status]} ({vix_ratio})")

        return "\n".join(lines)

    # 전 종목 요약
    lines = ["📊 종목 현황\n"]
    for sym, config in alert.SYMBOLS.items():
        ct = copper_trend if config.get("macro_filter") == "copper" else None
        result, error = alert.check_symbol(sym, config, copper_trend=ct)
        if error:
            lines.append(f"*{sym}* — 오류")
            continue
        r = result
        st = state_short.get(r["new_state"] if r["signal"] else r["state"], "?")
        rsi_bar = alert._rsi_bar(r["rsi"])
        action = alert._what_to_do(r)
        sig = ""
        if r["signal"]:
            sig_name = {"BUY": "🟢매수", "SELL": "🔴매도", "REBUY": "🟢재매수", "BUY_TIMING": "🔵매수적기"}
            sig = f" {sig_name.get(r['signal'], '')}"
        lines.append(f"*{sym}* ${r['price']:.2f} ({r['change_pct']:+.1f}%)")
        lines.append(f"RSI {r['rsi']:.0f} {rsi_bar} [{st}]{sig}")
        lines.append(f"→ {action}\n")

    # 매크로
    if copper_trend:
        trend_emoji = "📈" if copper_trend == "up" else "📉"
        lines.append(f"구리 {trend_emoji} ${copper_price:.2f}")
    if vix_status:
        vix_emoji = {"contango": "🟢", "neutral": "🟡", "backwardation": "🔴"}
        vix_label = {"contango": "콘탱고", "neutral": "중립", "backwardation": "백워데이션"}
        lines.append(f"VIX {vix_emoji[vix_status]} {vix_label[vix_status]} ({vix_ratio})")

    return "\n".join(lines)


def build_help():
    """/help 응답"""
    return (
        "📋 사용 가능한 명령어\n\n"
        "/status — 전 종목 현황 요약\n"
        "/status SOXL — 특정 종목 상세\n"
        "/help — 이 도움말\n\n"
        f"종목: {', '.join(alert.SYMBOLS.keys())}"
    )


def handle_message(msg):
    """메시지 파싱 → 명령어 분기"""
    text = msg.get("text", "")
    chat_id = str(msg["chat"]["id"])

    # 허용된 채팅만 응답
    if ALLOWED_CHAT_ID and chat_id != ALLOWED_CHAT_ID:
        return

    if text.startswith("/status"):
        parts = text.split()
        symbol = parts[1].upper() if len(parts) > 1 else None
        reply = build_status(symbol)
        send_reply(chat_id, reply)
    elif text.startswith("/help"):
        reply = build_help()
        send_reply(chat_id, reply)


def main():
    """Long polling 메인 루프"""
    print("Bot listener started. Waiting for commands...")
    offset = None
    while True:
        try:
            updates = get_updates(offset)
            for u in updates:
                if "message" in u:
                    handle_message(u["message"])
                offset = u["update_id"] + 1
        except KeyboardInterrupt:
            print("\nBot listener stopped.")
            break
        except Exception:
            traceback.print_exc()
            time.sleep(5)


if __name__ == "__main__":
    main()
