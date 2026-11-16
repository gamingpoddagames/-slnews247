import os
import requests


BOT_TOKEN = os.getenv("TG_TOKEN")
CHAT_ID = os.getenv("TG_CHAT_ID")


# ==========================================
# Upload Video To Telegram
# ==========================================

def upload_video(video_path, caption=""):

    if not BOT_TOKEN or not CHAT_ID:
        print("Telegram settings missing")
        return False

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendVideo"

    try:

        with open(video_path, "rb") as video:

            files = {
                "video": video
            }

            data = {
                "chat_id": CHAT_ID,
                "caption": caption[:1024],
                "supports_streaming": True
            }

            response = requests.post(
                url,
                data=data,
                files=files,
                timeout=600
            )

        print("Upload HTTP status:", response.status_code)

        if response.status_code == 200 and response.json().get("ok"):
            return True

        return False


    except Exception as e:

        print("Telegram request failed:", type(e).__name__)

        return False



# ==========================================
# Create Caption
# ==========================================

def make_caption(news):

    return f"""
{news['title_si']}

{news['summary_si']}

මූලාශ්‍රය: {news.get('source', '')}
{news.get('link', '')}

🌍 world news in sinhala
"""



# ==========================================
# Upload News
# ==========================================

def upload_news(video_path, news):

    caption = make_caption(news)

    return upload_video(
        video_path,
        caption
    )



# ==========================================
# Test
# ==========================================

if __name__ == "__main__":

    test = {
        "title_si": "Test News",
        "summary_si": "Telegram upload test"
    }

    print(
        upload_news(
            "output/news.mp4",
            test
        )
    )

