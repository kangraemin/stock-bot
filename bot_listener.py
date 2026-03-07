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
    """/status 응답 생성 — alert.py 공통 포맷 사용"""
    if symbol and symbol not in alert.SYMBOLS:
        available = ", ".join(alert.SYMBOLS.keys())
        return f"알 수 없는 종목: {symbol}\n사용 가능: {available}"

    copper_trend, copper_price, copper_sma = alert.get_copper_trend()
    vix_status, vix_ratio, vix_val = alert.get_vix_term()

    if symbol:
        config = alert.SYMBOLS[symbol]
        ct = copper_trend if config.get("macro_filter") == "copper" else None
        result, error = alert.check_symbol(symbol, config, copper_trend=ct)
        if error:
            return f"오류: {error}"
        return alert.format_single_report(result, copper_trend, copper_price,
                                          copper_sma, vix_status, vix_ratio, vix_val)

    # 전 종목
    results = []
    errors = []
    for sym, config in alert.SYMBOLS.items():
        ct = copper_trend if config.get("macro_filter") == "copper" else None
        result, error = alert.check_symbol(sym, config, copper_trend=ct)
        if error:
            errors.append(error)
        if result:
            results.append(result)

    if not results:
        return "모든 종목 데이터 실패"

    return alert.format_full_report(results, copper_trend, copper_price,
                                    copper_sma, vix_status, vix_ratio, vix_val, errors)


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
