"""Owner-authorized Blogger invitation; one attempt per destination per Colombo day."""
import json, os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import requests

URL = "https://slnews247live.blogspot.com/"
MESSAGE = """🇱🇰 Twenty Four Seven — පැය විසිහතර පුරාම — දැන් වෙබ් අඩවියෙන්!

වැදගත් පුවත් පැහැදිලි සිංහලෙන් කියවන්න. ශ්‍රී ලංකාවේ සිදුවීම්, ආර්ථිකය, අධ්‍යාපනය, ක්‍රීඩා සහ ලෝක පුවත් සඳහා අප සමඟ එක්වන්න.

🌐 වෙබ් අඩවියට පිවිසෙන්න:
https://slnews247live.blogspot.com/

📌 Bookmark කර තබාගන්න.
💬 ඔබේ අදහස් අපට කියන්න.
🤝 පුවත් කියවන්න කැමති මිතුරන් සමඟ බෙදාගන්න.

Twenty Four Seven"""
STATE = Path("data/blogger_invite_delivery.json")

def main():
    if os.getenv("PUBLISH_INVITE") != "true":
        print(MESSAGE)
        return
    # Public URL and ownership were verified in the signed-in browser at launch.
    # Blogger may reject runner requests even when the public site works.
    try:
        check = requests.get(URL, timeout=30)
        if check.status_code == 404:
            raise RuntimeError("News blog returned 404")
        print("Blog runner availability HTTP", check.status_code)
    except requests.RequestException:
        print("Blog availability probe unavailable; using browser-verified launch URL")
    day = datetime.now(ZoneInfo("Asia/Colombo")).date().isoformat()
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    record = state.setdefault(day, {})
    def save():
        STATE.parent.mkdir(exist_ok=True)
        STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2)+"\n")
    for dest in ("facebook", "telegram"):
        if dest in record:
            continue
        names = ("FB_PAGE_ID", "FB_PAGE_TOKEN") if dest == "facebook" else ("TG_TOKEN", "TG_CHAT_ID")
        if not all(os.getenv(n) for n in names):
            raise RuntimeError("Missing credentials for " + dest)
        record[dest] = {"status": "started", "url": URL}
        save()
        try:
            if dest == "facebook":
                response = requests.post("https://graph.facebook.com/v22.0/" + os.environ["FB_PAGE_ID"] + "/feed",
                    data={"access_token":os.environ["FB_PAGE_TOKEN"],"message":MESSAGE,"link":URL},timeout=45)
                result = response.json()
                ident = result.get("id") if response.ok else None
            else:
                response = requests.post("https://api.telegram.org/bot"+os.environ["TG_TOKEN"]+"/sendMessage",
                    json={"chat_id":os.environ["TG_CHAT_ID"],"text":MESSAGE},timeout=45)
                result = response.json()
                ident = result.get("result",{}).get("message_id") if response.ok and result.get("ok") else None
            record[dest] = {"status":"accepted" if ident else "rejected", "id":str(ident) if ident else None,"url":URL}
        except Exception:
            record[dest] = {"status":"unconfirmed","url":URL}
        save()
        print(dest + ": " + record[dest]["status"])
    if any(r["status"] != "accepted" for r in record.values()):
        raise RuntimeError("Invitation delivery needs review; do not blindly resend")
if __name__ == "__main__":
    main()
