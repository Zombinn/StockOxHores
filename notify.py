"""推送通知模块 — Telegram + 飞书"""
import os
import requests
from pathlib import Path

ENV_FILE = Path(__file__).parent / ".env"


def _read_env():
    """从 .env 读取配置"""
    cfg = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().split("\n"):
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                cfg[k.strip()] = v.strip()
    return cfg


# ─── Telegram ───

def send_telegram(text: str):
    cfg = _read_env()
    token = cfg.get("TELEGRAM_TOKEN", "")
    chat_id = cfg.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return False
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": int(chat_id), "text": text, "parse_mode": "Markdown",
                  "disable_web_page_preview": True},
            timeout=10,
        )
        return r.json().get("ok", False)
    except Exception:
        return False


# ─── 飞书 ───

FEISHU_HOOK = "https://open.feishu.cn/open-apis/bot/v2/hook/3175f12c-de88-4d43-ac8c-1dfda08fa2c2"


def send_feishu(text: str):
    """发送 Markdown 消息到飞书 bot"""
    if not FEISHU_HOOK:
        return False
    try:
        r = requests.post(
            FEISHU_HOOK,
            json={
                "msg_type": "interactive",
                "card": {
                    "header": {
                        "title": {"tag": "plain_text", "content": "📊 StockOxHores 情报简报"},
                        "template": "cyan"
                    },
                    "elements": [
                        {"tag": "markdown", "content": text}
                    ]
                }
            },
            timeout=10,
        )
        result = r.json()
        return result.get("code") == 0
    except Exception:
        return False


if __name__ == "__main__":
    ok = send_feishu("✅ StockOxHores 飞书推送测试成功")
    print(f"飞书测试: {'✅' if ok else '❌'}")
    ok2 = send_telegram("✅ StockOxHores 测试")
    print(f"Telegram测试: {'✅' if ok2 else '❌'}")
