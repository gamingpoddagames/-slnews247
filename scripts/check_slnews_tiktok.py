"""Print safe TikTok authorization diagnostics for SL NEWS 24/7."""
import json
import os

from slnews_tiktok import TikTokError, query_creator, verify_account


def main():
    mode = os.getenv("SLNEWS_TIKTOK_MODE", "off").lower()
    token = os.getenv("SLNEWS_TIKTOK_ACCESS_TOKEN", "")
    open_id = os.getenv("SLNEWS_TIKTOK_EXPECTED_OPEN_ID", "")
    print("SL News TikTok mode:", mode)
    print("Dedicated news account token configured:", bool(token))
    print("Expected news account open ID configured:", bool(open_id))
    if mode == "off":
        print("Result: OFF. No TikTok uploads are attempted.")
        return
    try:
        verify_account(token, open_id)
        print("News account identity: verified")
    except TikTokError as exc:
        print("News account identity: NOT READY", exc.code)
        return
    except Exception as exc:
        print("News account network check: unavailable", type(exc).__name__)
        return
    if mode == "direct":
        try:
            creator = query_creator(token)
            username = creator.get("creator_username")
            expected = os.getenv("SLNEWS_TIKTOK_EXPECTED_USERNAME", "").lstrip("@")
            print("video.publish creator_info access: confirmed")
            print("Correct news username:", bool(username and expected and username == expected))
            print("Privacy options:", ",".join(creator.get("privacy_level_options") or []))
            print("Per-video review required before every Direct Post")
        except TikTokError as exc:
            print("video.publish authorization: NOT READY", exc.code)
        except Exception as exc:
            print("Creator info request unavailable", type(exc).__name__)
    elif mode == "draft":
        print("News account verified. video.upload scope is verified on first draft init.")
    else:
        print("Invalid mode; TikTok worker will use OFF.")


if __name__ == "__main__":
    main()
