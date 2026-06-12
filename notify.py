"""Telegram 推送通知模块"""
import requests

BOT_TOKEN = "8727873270:AAFygq8rPNAY5mo7shTX_1YCsqGeEFEftRY"
BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"


def get_updates():
    """获取最近的对话，找到 chat_id"""
    try:
        r = requests.get(f"{BASE_URL}/getUpdates", timeout=10)
        data = r.json()
        chats = set()
        for update in data.get("result", []):
            msg = update.get("message", {})
            chat = msg.get("chat", {})
            chat_id = chat.get("id")
            chat_name = chat.get("first_name") or chat.get("title") or str(chat_id)
            chats.add((chat_id, chat_name))
        return list(chats)
    except Exception:
        return []


def send_message(chat_id, text, parse_mode="Markdown"):
    """发送消息到指定 chat_id"""
    try:
        r = requests.post(
            f"{BASE_URL}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": parse_mode,
                "disable_web_page_preview": True,
            },
            timeout=10,
        )
        return r.json().get("ok", False)
    except Exception:
        return False


def send_telegram(text: str):
    """发送消息到所有已知的 Telegram 对话"""
    chats = get_updates()
    ok = False
    for chat_id, _ in chats:
        if send_message(chat_id, text):
            ok = True
    return ok


if __name__ == "__main__":
    chats = get_updates()
    print("已知对话:")
    for chat_id, name in chats:
        print(f"  {chat_id}: {name}")

    if chats:
        chat_id, name = chats[0]
        ok = send_message(chat_id, "✅ StockOxHores 通知测试成功")
        print(f"\n发送测试消息到 {name}: {'✅' if ok else '❌'}")
    else:
        print("❌ 没有找到对话。请先在 Telegram 上给 bot 发一条消息。")
