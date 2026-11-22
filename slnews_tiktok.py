"""TikTok publishing handoff for EXISTING SL NEWS 24/7 news reels.

Unlike Facebook/Telegram uploads, TikTok requires a creator-authorized app.
Default OFF. DRAFT mode uploads to the account's inbox (creator completes
posting); DIRECT mode requires per-video approval in the reviewed manifest.
No raw token, refresh secret or signed upload URL is ever written to logs.

All submissions are journaled *before* external requests to avoid duplicate
posts when GitHub Actions retries after an ambiguous network response.
"""
import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

API = "https://open.tiktokapis.com/v2"
APPROVALS = Path("data/tiktok_approved_posts.json")
MODES = {"off", "draft", "direct"}


class TikTokError(Exception):
    def __init__(self, code="tiktok_api_error"):
        self.code = str(code)[:80]
        super().__init__(self.code)


def _headers(token):
    return {"Authorization": "Bearer " + token,
            "Content-Type": "application/json; charset=UTF-8"}


def _data(reply):
    """Decode TikTok result, never persist raw responses containing secrets."""
    try:
        payload = reply.json()
    except (ValueError, TypeError):
        raise TikTokError("invalid_api_response")
    code = (payload.get("error") or {}).get("code", "unknown")
    if reply.status_code != 200 or code != "ok":
        raise TikTokError(code)
    return payload.get("data") or {}


def _post(token, url, data=None, session=requests):
    result = session.post(API + url, headers=_headers(token), json=data,
                          timeout=(6, 25))
    return _data(result)


def verify_account(token, expected_open_id, session=requests):
    """Never use a potentially connected trading/news account by mistake."""
    if not token:
        raise TikTokError("missing_news_account_token")
    if not expected_open_id:
        raise TikTokError("missing_expected_news_open_id")
    result = session.get(
        API + "/user/info/?fields=open_id,display_name",
        headers={"Authorization": "Bearer " + token}, timeout=(6, 25))
    user = _data(result).get("user") or {}
    if not user.get("open_id"):
        raise TikTokError("user_info_basic_not_authorized")
    if user["open_id"] != expected_open_id:
        raise TikTokError("wrong_tiktok_account")
    return {"open_id_verified": True, "display_name": user.get("display_name", "")}


def query_creator(token, session=requests):
    return _post(token, "/post/publish/creator_info/query/", session=session)


def _duration(video_path):
    process = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)],
        capture_output=True, check=True, text=True, timeout=15)
    return float(process.stdout.strip())


def _file_info(path):
    target = Path(path)
    if target.suffix.lower() != ".mp4" or not target.is_file():
        raise TikTokError("missing_mp4")
    size = target.stat().st_size
    if not 20480 <= size <= 60 * 1024 * 1024:
        raise TikTokError("invalid_mp4_size")
    return size


def build_caption(article, photo_credit=""):
    """Only story facts, news brand, optional legally required image credit."""
    title = article.get("title_si", "").strip()
    if not title:
        raise TikTokError("empty_headline")
    summary = article.get("summary_si", "").strip()
    extra = str(photo_credit or "").strip()
    suffix = "\n\n#SLNews247 #SinhalaNews #SriLankaNews"
    # Credits are never truncated. Shorten the editorial summary instead.
    prefix = "🔴 " + title[:180]
    room = max(0, 1500 - len(prefix) - len(suffix) - len(extra) - 8)
    if room and summary:
        sentences = [piece.strip() for piece in
                     __import__("re").split(r"(?<=[.!?।])\s+", summary)]
        chosen = []
        for sentence in sentences:
            if sentence and (len(" ".join(chosen + [sentence])) <= room):
                chosen.append(sentence)
            else:
                break
        if chosen:
            prefix += "\n\n" + " ".join(chosen)
    if extra:
        prefix += "\n\n" + extra
    return prefix + suffix


def _approved_direct(article, creator):
    """TikTok requires creator interaction/consent for each direct post."""
    try:
        approvals = json.loads(APPROVALS.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None
    review = (approvals.get("articles") or {}).get(article["id"]) or {}
    if review.get("approved") is not True:
        return None
    expected_url = (article.get("link") or "").strip()
    if review.get("article_url") != expected_url:
        return None
    privacy = review.get("privacy_level")
    if privacy not in (creator.get("privacy_level_options") or []):
        return None
    # An unaudited client must not send public Direct Posts.
    if privacy != "SELF_ONLY" and os.getenv("SLNEWS_TIKTOK_APP_AUDITED", "false").lower() != "true":
        return None
    if "PUBLIC_TO_EVERYONE" == privacy and not os.getenv("SLNEWS_TIKTOK_EXPECTED_USERNAME"):
        return None
    nickname = str(creator.get("creator_username") or "").casefold().lstrip("@")
    expected = os.getenv("SLNEWS_TIKTOK_EXPECTED_USERNAME", "").casefold().lstrip("@")
    if not expected or nickname != expected:
        return None
    return review


def _init_upload(token, size, mode, caption, review, creator, session=requests):
    source = {"source": "FILE_UPLOAD", "video_size": size,
              "chunk_size": size, "total_chunk_count": 1}
    if mode == "draft":
        endpoint = "/post/publish/inbox/video/init/"
        payload = {"source_info": source}
    else:
        info = {
            "title": caption,
            "privacy_level": review["privacy_level"],
            "disable_comment": bool(creator.get("comment_disabled", False)),
            "disable_duet": bool(creator.get("duet_disabled", False)),
            "disable_stitch": bool(creator.get("stitch_disabled", False)),
            "brand_content_toggle": False,
            "brand_organic_toggle": False,
        }
        payload = {"post_info": info, "source_info": source}
        endpoint = "/post/publish/video/init/"
    data = _post(token, endpoint, payload, session=session)
    if not data.get("publish_id") or not data.get("upload_url"):
        raise TikTokError("publish_init_missing_identifiers")
    return data


def _put_video(upload_url, path, session=requests):
    parsed = urlparse(upload_url)
    # An untrusted redirect must not cause file upload to another server.
    if parsed.scheme != "https" or parsed.hostname != "open-upload.tiktokapis.com":
        raise TikTokError("unsafe_upload_destination")
    size = _file_info(path)
    with open(path, "rb") as video:
        response = session.put(
            upload_url, data=video,
            headers={"Content-Type": "video/mp4",
                     "Content-Length": str(size),
                     "Content-Range": f"bytes 0-{size-1}/{size}"},
            timeout=(7, 180))
    if response.status_code not in (200, 201, 206):
        raise TikTokError("video_upload_rejected")
    return True


def _check_status(token, publish_id, session=requests):
    return _post(token, "/post/publish/status/fetch/",
                 {"publish_id": publish_id}, session=session)


def _limits(journal, now):
    max_day = max(1, min(5, int(os.getenv("SLNEWS_TIKTOK_MAX_PER_DAY", "2"))))
    sent = sorted(x.get("submitted_at", 0) for x in journal.values()
                  if x.get("submitted_at", 0) and now - x["submitted_at"] < 86400)
    if len(sent) >= max_day:
        return False, "daily_tiktok_limit"
    if sent and now - sent[-1] < 3 * 3600:
        return False, "three_hour_tiktok_interval"
    return True, "ok"


def process_tiktok_queue(state, now, preview=False, render=None,
                         save=None, session=requests):
    """Advance queued news reels into creator-authorized TikTok delivery.

    The caller owns saving state to the same merged GitHub checkpoint used by
    Facebook and Telegram. No network or upload happens in preview/off mode.
    """
    mode = os.getenv("SLNEWS_TIKTOK_MODE", "off").lower()
    if mode not in MODES:
        mode = "off"
    journal = state.setdefault("tiktok_news", {})
    reels = state.get("reels") or {}
    boundary = state.setdefault("tiktok_started_at", now)
    result = {"mode": mode, "status": "ready", "queued": 0, "submitted": 0,
              "published": 0, "inbox": 0, "errors": []}
    # Old reels already sent to FB/TG are not blasted to the news account.
    for story_id, info in reels.items():
        if (story_id not in journal and info.get("at", 0) >= boundary
                and info.get("status") == "delivered" and info.get("article")):
            journal[story_id] = {"article": info["article"],
                                 "status": "queued", "queued_at": now}
    result["queued"] = sum(x.get("status") == "queued" for x in journal.values())
    if preview:
        result["status"] = "preview_only"
        return result
    if mode == "off":
        result["status"] = "setup_required"
        return result
    token = os.getenv("SLNEWS_TIKTOK_ACCESS_TOKEN", "")
    open_id = os.getenv("SLNEWS_TIKTOK_EXPECTED_OPEN_ID", "")
    try:
        verify_account(token, open_id, session=session)
    except (TikTokError, requests.RequestException) as exc:
        result["status"] = "account_authorization_required"
        result["errors"].append(exc.code if isinstance(exc, TikTokError) else "network_error")
        return result

    # Status reconciliation FIRST. Never upload a duplicate while TikTok is
    # still processing an earlier publish_id or upload is ambiguous.
    for record in journal.values():
        if not record.get("publish_id") or record.get("status") in (
                "published", "failed_review_required"):
            continue
        try:
            status = _check_status(token, record["publish_id"],
                                   session=session)
            value = status.get("status")
            record["tiktok_status"] = value
            if value == "PUBLISH_COMPLETE":
                record["status"] = "published"
                result["published"] += 1
            elif value == "SEND_TO_USER_INBOX":
                record["status"] = "inbox_ready_for_creator"
                result["inbox"] += 1
            elif value == "FAILED":
                record["status"] = "failed_review_required"
                record["fail_reason"] = str(status.get("fail_reason", "unknown"))[:70]
            else:
                record["status"] = "processing"
            if save:
                save(state)
        except (TikTokError, requests.RequestException):
            # Keep publish_id; do not retry upload or risk duplicates.
            result["errors"].append("status_check_pending")
    allowed, why = _limits(journal, now)
    if not allowed:
        result["status"] = why
        return result

    candidates = sorted(
        ((k, v) for k, v in journal.items() if v.get("status") == "queued"),
        key=lambda pair: pair[1].get("queued_at", 0))
    if not candidates:
        result["status"] = "no_new_tiktok_reels"
        return result

    creator = None
    if mode == "direct":
        try:
            creator = query_creator(token, session=session)
        except (TikTokError, requests.RequestException) as exc:
            result["status"] = "direct_post_scope_or_app_review_required"
            result["errors"].append(exc.code if isinstance(exc, TikTokError)
                                    else "network_error")
            return result
    candidate = None
    review = None
    for key, entry in candidates:
        if mode == "direct":
            permission = _approved_direct(entry["article"], creator)
            if permission is None:
                continue
            review = permission
        candidate = (key, entry)
        break
    if candidate is None:
        result["status"] = "awaiting_per_video_creator_approval"
        return result
    if render is None:
        from story_reels import _render_reel
        render = _render_reel
    key, entry = candidate
    article = entry["article"]
    target = str(Path("output/tiktok_reels") / (key + ".mp4"))
    Path(target).parent.mkdir(parents=True, exist_ok=True)
    try:
        video, style = render(article, target)
        size = _file_info(video)
        if mode == "direct":
            duration = _duration(video)
            if not 3 <= duration <= min(90, creator.get("max_video_post_duration_sec", 90)):
                raise TikTokError("creator_video_duration_restriction")
        from story_reels import _media_attribution, _approved_asset_attribution
        credit = (_approved_asset_attribution(article, 'video')
                  if style == 'approved_exact_event_clip'
                  else _media_attribution(article))
        title = build_caption(article, credit)
    except (OSError, ValueError, TikTokError, subprocess.SubprocessError) as exc:
        result["status"] = "render_retry_next_run"
        result["errors"].append(exc.code if isinstance(exc, TikTokError)
                                else type(exc).__name__)
        return result

    # Record intent before API action; ambiguous network errors require
    # inspection. Never silently reuse a submitted video.
    entry.update(status="submission_unconfirmed",
                 submitted_at=now, mode=mode, media_style=style)
    if save:
        save(state)
    try:
        response = _init_upload(token, size, mode, title, review, creator,
                                session=session)
        entry["publish_id"] = response["publish_id"]
        if save:
            save(state)
        _put_video(response["upload_url"], video, session=session)
        entry["status"] = "processing"
        result["submitted"] += 1
        result["status"] = "uploaded_waiting_tiktok_status"
    except (TikTokError, requests.RequestException) as exc:
        entry["status"] = "submission_unconfirmed"
        result["status"] = "submission_requires_review"
        result["errors"].append(exc.code if isinstance(exc, TikTokError)
                                else "network_error")
    if save:
        save(state)
    return result
