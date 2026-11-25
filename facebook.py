import os
import requests


GRAPH_VERSION = "v22.0"

PAGE_ID = os.getenv("FB_PAGE_ID")
PAGE_TOKEN = os.getenv("FB_PAGE_TOKEN")

PAGE_URL = "https://www.facebook.com/1020689164470492"
TELEGRAM_URL = "https://t.me/slnews247"


def with_follow_links(text):
    """Owner-approved channel links for Facebook posts and video descriptions."""
    text = str(text or '').rstrip()
    additions = []
    if PAGE_URL not in text:
        additions.append('අලුත් පුවත් සඳහා SL NEWS 24/7 Follow කරන්න.\n' + PAGE_URL)
    if TELEGRAM_URL not in text:
        additions.append('තවත් පුවත් සඳහා අපේ Telegram channel එකට එක්වන්න.\n' + TELEGRAM_URL)
    return '\n\n'.join([text] + additions)


# ==========================================
# Create Caption
# ==========================================

def make_caption(news):
    from fast_news import caption
    return with_follow_links(caption(news))


# ==========================================
# Upload Video To Facebook Page
# ==========================================

def upload_video(video_path, caption):

    if not PAGE_ID or not PAGE_TOKEN:

        print("Facebook settings missing")

        return False


    url = (
        f"https://graph.facebook.com/"
        f"{GRAPH_VERSION}/"
        f"{PAGE_ID}/videos"
    )


    try:

        with open(video_path, "rb") as video:

            files = {
                "source": video
            }


            data = {

                "description": with_follow_links(caption),

                "access_token": PAGE_TOKEN

            }


            response = requests.post(

                url,

                files=files,

                data=data,

                timeout=600

            )


        print("Upload HTTP status:", response.status_code)


        if response.status_code == 200 and response.json().get("id"):

            return True


        return False


    except Exception as e:

        print("Facebook request failed:", type(e).__name__)

        return False



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

    test_news = {

        "title_si": "Test News",

        "summary_si": "Facebook upload test"

    }


    print(

        upload_news(

            "output/news.mp4",

            test_news

        )

    )


