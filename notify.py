"""Telegram 推送通知模块"""
import os
import requests

# 从 .env 加载 token
_token = os.getenv("TELEGRAM_TOKEN")
if not _token:
    try:
        from pathlib import Path
        env_file = Path(__file__).parent / ".env"
        for line in env_file.read_text().split("\n"):
            if line.startswith("TELEGRAM_TOKEN="):
                _token = line.split("=", 1)[1].strip()
    except:
        pass
BOT_TOKEN = _token or ""

# chat_id 从 .env 持久化读取
_chat_id = os.getenv("TELEGRAM_CHAT_ID")
if not _chat_id:
    try:
        from pathlib import Path
        env_file = Path(__file__).parent / ".env"
        for line in env_file.read_text().split("\n"):
            if line.startswith("TELEGRAM_CHAT_ID="):
                _chat_id = line.split("=", 1)[1].strip()
    except:
        pass
CHAT_ID = _chat_id or ""

BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"


def send_message(text, parse_mode="Markdown"):
    """发送消息到持久化的 chat_id"""
    if not CHAT_ID:
        return False
    try:
        r = requests.post(
            f"{BASE_URL}/sendMessage",
            json={
                "chat_id": int(CHAT_ID),
                "text": text,
                "parse_mode": parse_mode,
                "disable_web_page_preview": True,
            },
            timeout=10,
        )
        return r.json().get("ok", False)
    except Exception:
        return False


def send_telegram(text: str, parse_mode="Markdown"):
    """发送消息"""
    return send_message(text, parse_mode=parse_mode)


if __name__ == "__main__":
    ok = send_message("✅ StockOxHores 通知测试", parse_mode="Markdown")
    print(f"发送测试: {'✅' if ok else '❌'}")
