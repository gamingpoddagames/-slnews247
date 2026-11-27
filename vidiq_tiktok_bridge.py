"""Direct Public TikTok delivery in the existing GitHub news/Blogger run.

GitHub OIDC authenticates to the owner's encrypted vidIQ connection. No vidIQ
or TikTok credential is stored in this repository or returned to the runner.
"""
import io
import json
import os
import re
import shlex
import subprocess
import time
import zipfile
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path
from urllib.parse import quote, urlsplit

import requests

BRIDGE = "https://everydaykit.gamingpoddagames.workers.dev/slnews247/vidiq"
ACCOUNT = "_000pSUDUpUO5p3zoi4neSwWWUIyukn4lGIr"
REPO = "gamingpoddagames/-slnews247"
LEGACY = {
    "46ca827eecb3842ff5d80d1c": ("72d2017c-43a2-4a5d-8061-961d29b31063",
        "376032b9-ec0a-471a-b827-3e1221aa3507",
        "https://www.tiktok.com/@slnewstwentyfourseven/video/7712911133153185044"),
    "cbf98e8c42bbfc5701da1041": ("71185dc9-bd5e-4470-afc7-2e12ef8da5e8",
        "9e1b2497-298b-4e90-8449-ab298565cda9",
        "https://www.tiktok.com/@slnewstwentyfourseven/video/7712920636410088710"),
}


class BridgeError(Exception):
    pass


def unpack(result):
    if isinstance(result.get("structuredContent"), dict):
        return result["structuredContent"]
    for item in result.get("content", []):
        if item.get("type") == "text":
            try:
                return json.loads(item["text"])
            except (ValueError, KeyError):
                pass
    return result


def settings():
    return dict(platform="TIKTOK", platformAccountId=ACCOUNT,
                privacyLevel="PUBLIC_TO_EVERYONE", allowComment=True,
                autoAddMusic=False, musicUsageConfirmed=True)


class Publisher:
    def __init__(self, story):
        self.story = story
        self.session = ""
        self.sequence = 0
        self.identity = ""
        self.identity_until = 0

    def oidc(self):
        if time.time() >= self.identity_until:
            url = os.getenv("ACTIONS_ID_TOKEN_REQUEST_URL", "")
            token = os.getenv("ACTIONS_ID_TOKEN_REQUEST_TOKEN", "")
            if not url or not token:
                raise BridgeError("github_identity_required")
            url += ("&" if "?" in url else "?") + "audience=" + quote("slnews247-vidiq-publisher")
            response = requests.get(url, headers={"Authorization": "Bearer " + token}, timeout=(5, 20))
            response.raise_for_status()
            self.identity = response.json()["value"]
            self.identity_until = time.time() + 240
        return self.identity

    def headers(self):
        result = {"Authorization": "Bearer " + self.oidc(), "X-SLNews-Story": self.story}
        if self.session:
            result["Mcp-Session-Id"] = self.session
        return result

    def connected(self):
        response = requests.get(BRIDGE + "/status", headers=self.headers(), timeout=(5, 20))
        response.raise_for_status()
        return response.json().get("connected") is True

    def rpc(self, method, params):
        self.sequence += 1
        payload = dict(jsonrpc="2.0", method=method, params=params)
        if method != "notifications/initialized":
            payload["id"] = self.sequence
        response = requests.post(BRIDGE + "/mcp", headers=self.headers(), json=payload, timeout=(8, 70))
        if not response.ok:
            try:
                error = response.json().get("error", "bridge_unavailable")
            except ValueError:
                error = "bridge_unavailable"
            raise BridgeError(str(error) if re.fullmatch(r"[a-z_]+", str(error)) else "bridge_unavailable")
        self.session = response.headers.get("Mcp-Session-Id", self.session)
        body = response.json()
        if "error" in body:
            raise BridgeError("mcp_request_failed")
        return body.get("result", {})

    def start(self):
        self.rpc("initialize", dict(protocolVersion="2025-06-18", capabilities={},
            clientInfo=dict(name="SL NEWS 24/7 GitHub publisher", version="1.0")))
        self.rpc("notifications/initialized", {})
        accounts = self.tool("vidiq_social_account_list", dict(platform="TIKTOK")).get("accounts", [])
        if not any(a.get("platformAccountId") == ACCOUNT and a.get("canPublish") is True for a in accounts):
            raise BridgeError("wrong_or_unavailable_news_account")

    def tool(self, name, arguments):
        result = self.rpc("tools/call", dict(name=name, arguments=arguments))
        if result.get("isError"):
            raise BridgeError("publishing_tool_refused")
        return unpack(result)


def transfer_parts(command, path, upload_id):
    """Interpret only documented transfer arguments; never execute server code."""
    args = shlex.split(command)
    if len(args) != 9 or Path(args[0]).name != "sh" or args[1] != "-c" or args[3] != "vidiq-upload":
        raise BridgeError("unsupported_transfer_protocol")
    if args[4] != str(path.resolve()) or args[5] != str(path.stat().st_size) or args[7] != "video/mp4" or args[8] != upload_id:
        raise BridgeError("transfer_identity_mismatch")
    u = urlsplit(args[6])
    if u.scheme != "https" or u.hostname != "storage.googleapis.com":
        raise BridgeError("unsafe_transfer_destination")
    return args[6]


def upload_video(client, path):
    probe = subprocess.run(['ffprobe', '-v', 'error', '-show_streams', '-of', 'json', str(path)],
                           capture_output=True, text=True, timeout=30, check=True)
    streams = json.loads(probe.stdout)['streams']
    video = next((s for s in streams if s.get('codec_type') == 'video'), {})
    if not any(s.get('codec_type') == 'audio' for s in streams):
        raise BridgeError('narration_required')
    fps = Fraction(video.get('avg_frame_rate', '0/1'))
    if video.get('codec_name') != 'h264' or not 23 <= fps <= 60:
        target = path.with_name(path.stem + '_tiktok30.mp4')
        subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', str(path),
                        '-vf', 'fps=30', '-c:v', 'libx264', '-preset', 'veryfast',
                        '-crf', '23', '-c:a', 'aac', '-movflags', '+faststart', str(target)],
                       capture_output=True, timeout=240, check=True)
        path = target
    result = client.tool("vidiq_video_upload", dict(localFile=dict(
        path=str(path.resolve()), sizeBytes=path.stat().st_size, contentType="video/mp4"),
        title="SL NEWS 24/7 original news reel"))
    upload_id = result.get("uploadId")
    if not upload_id:
        raise BridgeError("upload_not_started")
    if result.get("status") != "ready":
        url = transfer_parts(result.get("command", ""), path, upload_id)
        response = requests.post(url, headers={"x-goog-resumable": "start",
            "x-upload-content-type": "video/mp4", "x-upload-content-length": str(path.stat().st_size),
            "Content-Length": "0"}, data=b"", timeout=(8, 60), allow_redirects=False)
        session = response.headers.get("Location", "")
        if response.status_code not in (200, 201) or urlsplit(session).scheme != "https" or urlsplit(session).hostname != "storage.googleapis.com":
            raise BridgeError("storage_session_refused")
        with path.open("rb") as stream:
            sent = requests.put(session, data=stream, headers={
                "Content-Length": str(path.stat().st_size), "Content-Type": "video/mp4"},
                timeout=(8, 150), allow_redirects=False)
        if sent.status_code not in (200, 201):
            raise BridgeError("video_transfer_incomplete")
        for _ in range(6):
            result = client.tool("vidiq_video_upload", dict(uploadId=upload_id))
            if result.get("status") == "ready":
                break
            if result.get("status") == "failed":
                raise BridgeError("video_import_failed")
            time.sleep(3)
        else:
            raise BridgeError("video_import_pending")
    return dict(id=upload_id, type="video")


def upload_image(client, path):
    from PIL import Image
    target = path.with_name(path.stem + "_tiktok.jpg")
    with Image.open(path) as image:
        image = image.convert("RGB")
        image.thumbnail((1080, 1080))
        image.save(target, quality=94)
    result = client.tool("vidiq_upload_image", dict(fileName=target.name))
    url = result.get("uploadUrl", "")
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not (parsed.hostname == "storage.googleapis.com" or
            parsed.hostname == "mcp.vidiq.com" and parsed.path.startswith('/mcp/uploads/images/')):
        raise BridgeError("unsafe_image_transfer")
    with target.open("rb") as stream:
        response = requests.put(url, data=stream, headers={"Content-Type": "image/jpeg"},
                                timeout=(8, 90), allow_redirects=False)
    if not response.ok:
        raise BridgeError("image_transfer_incomplete")
    result = client.tool("vidiq_upload_image", dict(transferId=result["transferId"]))
    if not result.get("imageId"):
        raise BridgeError("image_import_pending")
    return dict(id=result["imageId"], type="image")


def recover_media(story_id, kind, path):
    """Fetch only this story's own original asset from prior main-run artifacts."""
    token = os.getenv("SLNEWS_ARTIFACT_READ_TOKEN", "")
    if not token:
        return False
    response = requests.get("https://api.github.com/repos/" + REPO + "/actions/artifacts?per_page=30",
                            headers={"Authorization": "Bearer " + token}, timeout=(5, 25))
    response.raise_for_status()
    name = ("reels/" + story_id + ".mp4" if kind == "reel" else "card_" + story_id + ".png")
    for item in response.json().get("artifacts", [])[:12]:
        run = item.get("workflow_run", {})
        if item.get("expired") or run.get("head_branch") != "main" or not item.get("name", "").startswith("sinhala-news-"):
            continue
        if int(item.get("size_in_bytes", 0)) > 40_000_000:
            continue
        archive = requests.get(item["archive_download_url"], headers={"Authorization": "Bearer " + token},
                               timeout=(8, 100))
        archive.raise_for_status()
        if len(archive.content) > 40_000_000:
            continue
        with zipfile.ZipFile(io.BytesIO(archive.content)) as zipped:
            if name not in zipped.namelist():
                continue
            info = zipped.getinfo(name)
            if info.file_size > 30_000_000:
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(zipped.read(info))
            manifest = name + '.attribution.json'
            if manifest in zipped.namelist():
                Path(str(path) + '.attribution.json').write_bytes(zipped.read(manifest))
            else:
                credits = []
                for member in zipped.namelist():
                    if not member.endswith('.credit.json') or zipped.getinfo(member).file_size > 20000:
                        continue
                    try:
                        item = json.loads(zipped.read(member))
                    except (ValueError, UnicodeError):
                        continue
                    if item.get('article_id') == story_id:
                        credits.append(item)
                if credits:
                    required = ['📷 ' + c['creator'] + ' · ' + c['license'] + ' (cropped/resized). '
                                + c['source'] + ' ' + c['license_url'] for c in credits
                                if c.get('provider') != 'Pexels']
                    Path(str(path) + '.attribution.json').write_text(json.dumps({
                        'article_id': story_id, 'attribution': '\n\n' + '\n'.join(required) if required else ''},
                        ensure_ascii=False), encoding='utf-8')
            return True
    return False


def caption_for(article, path=None):
    from fast_news import caption
    text = caption(article)
    # All still-image/reel credits are retained when their actual licence needs
    # attribution. Pexels does not require an extra public credit line.
    manifest = Path(str(path) + '.attribution.json') if path is not None else None
    if manifest is None or not manifest.is_file():
        raise BridgeError('media_provenance_unavailable')
    metadata = json.loads(manifest.read_text(encoding='utf-8'))
    if metadata.get('article_id') != article['id']:
        raise BridgeError('media_provenance_mismatch')
    credit = metadata.get('attribution', '')
    if "Pexels stock:" in credit or "Pexels context:" in credit:
        credit = ""
    if len(text + credit) > 2200:
        text = "🔴 " + article["title_si"] + "\n\nSL NEWS 24/7"
    if len(text + credit) > 2200:
        raise BridgeError("required_credit_exceeds_caption_limit")
    return text + credit


def reconcile(client, entry, state, save):
    if not entry.get("postId") or not entry.get("publicationId"):
        return
    response = client.tool("vidiq_social_post_status", dict(
        postId=entry["postId"], publicationId=entry["publicationId"]))
    item = next((d for d in response.get("destinations", []) if d.get("publicationId") == entry["publicationId"]), None)
    if item:
        entry.update(status=item["status"], postUrl=item.get("postUrl"), failureCode=item.get("failureCode"),
                     failureReason=item.get("failureReason"), checked_at=time.time())
        save(state)


def matching_history(client, title, now):
    """Query filtering happens after pagination; an empty page is not final."""
    arguments = dict(platforms=["TIKTOK"], platformAccountIds=[ACCOUNT],
        query=title, **{"from": datetime.fromtimestamp(now-43200, timezone.utc).isoformat(),
        "to": datetime.fromtimestamp(now+60, timezone.utc).isoformat()}, limit=50)
    rows, seen = [], set()
    for _ in range(20):
        response = client.tool("vidiq_social_post_list", arguments)
        rows.extend(response.get("destinations", []))
        cursor = response.get("nextCursor")
        if not cursor:
            return rows
        if cursor in seen:
            break
        seen.add(cursor)
        arguments["cursor"] = cursor
    raise BridgeError("history_reconciliation_incomplete")


def publish_tiktok(state, articles, now, preview=False, save=None, max_items=3):
    """Publish in this production run; no timer, inbox mode or future schedule."""
    result = dict(mode="direct_public", status="disabled", sent=0, pending=0, errors=[])
    if preview:
        return dict(result, status="preview")
    if os.getenv("SLNEWS_VIDIQ_BRIDGE_URL", "").rstrip("/") != BRIDGE:
        return result
    if os.getenv('SLNEWS_VIDIQ_PUBLISH_ENABLED', 'false').lower() != 'true':
        return dict(result, status='awaiting_owner_connection')
    if 0 <= now - state.get('vidiq_tiktok_limit_at', -86400) < 86400:
        return dict(result, status='platform_limit')
    save = save or (lambda _: None)
    candidates = {}
    for article in articles:
        ident = str(article.get("id", ""))
        if not re.fullmatch(r"[a-f0-9]{24}", ident) or not 0 <= now - article.get("published", 0) <= 43200:
            continue
        record = state.get("stories", {}).get(ident, {})
        blog = state.get("blogger_posts", {}).get(ident, {})
        if not any(r.get("id") for r in record.get("receipts", {}).values() if isinstance(r, dict)) and not blog.get("id"):
            continue
        reel = state.get("reels", {}).get(ident, {})
        kind = "reel" if any(v == "accepted" for v in reel.get("destinations", {}).values()) else "photo"
        candidates[ident] = (article, kind)
    if not candidates:
        return dict(result, status="no_new_items")
    journal = state.setdefault("vidiq_tiktok", {})
    client = Publisher(next(iter(candidates)) + ":photo")
    try:
        if not client.connected():
            return dict(result, status="connection_required")
        client.start()
    except (BridgeError, requests.RequestException, ValueError, KeyError):
        return dict(result, status="connection_unavailable")
    result["status"] = "ready"
    attempted = 0
    for ident, (article, kind) in sorted(candidates.items(), key=lambda item: item[1][0]["published"], reverse=True):
        if ident in LEGACY:
            post, publication, url = LEGACY[ident]
            journal.setdefault(ident, dict(status="completed", postId=post, publicationId=publication, postUrl=url))
            continue
        entry = journal.setdefault(ident, {})
        if entry.get("status") in ("completed", "failed", "reconciliationRequired"):
            continue
        if entry.get('status') in ('uncertain', 'creating') and not (entry.get('postId') and entry.get('publicationId')):
            continue
        client.story = ident + ":" + entry.get("kind", kind)
        if entry.get("postId") and entry.get("publicationId"):
            try:
                if entry.get('status') == 'draft':
                    draft = client.tool('vidiq_social_post_draft_get', dict(postId=entry['postId']))
                    if not draft.get('ready') or draft.get('text') != entry.get('caption'):
                        entry['status'] = 'reconciliationRequired'
                        save(state)
                        continue
                    sent = client.tool('vidiq_social_post_publish', dict(postId=entry['postId'],
                        revision=draft['revision'], publicationIds=[entry['publicationId']]))
                    entry['status'] = next((d['status'] for d in sent.get('destinations', [])
                        if d.get('publicationId') == entry['publicationId']), 'uncertain')
                    save(state)
                reconcile(client, entry, state, save)
            except (BridgeError, requests.RequestException, ValueError, KeyError):
                pass
            continue
        if attempted >= max_items:
            result["pending"] += 1
            continue
        attempted += 1
        path = Path("output/reels/" + ident + ".mp4") if kind == "reel" else Path("output/card_" + ident + ".png")
        try:
            if not path.is_file() and not recover_media(ident, kind, path):
                result["pending"] += 1
                continue
            # Locate earlier connector delivery before creating anything new.
            history = matching_history(client, article["title_si"], now)
            found = next((p for p in history if p.get("status") == "completed"), None)
            if found:
                entry.update(status="completed", postId=found["postId"], publicationId=found["publicationId"], postUrl=found.get("postUrl"))
                save(state)
                continue
            if history:
                entry.update(status="reconciliationRequired", checked_at=now)
                save(state)
                continue
            entry.update(kind=kind, status="importing", checked_at=now)
            save(state)
            media = upload_video(client, path) if kind == "reel" else upload_image(client, path)
            text = caption_for(article, path)
            entry.update(status="creating", media_id=media["id"], caption=text)
            save(state)
            draft = client.tool("vidiq_social_post_draft_create", dict(
                text=text, media=[media], destinations=[settings()]))
            dest = next((d for d in draft.get("destinations", []) if d.get("platformAccountId") == ACCOUNT), {})
            if draft.get("postId"):
                entry.update(postId=draft["postId"], publicationId=dest.get("publicationId"),
                             revision=draft.get("revision"), status="reconciliationRequired")
                save(state)
            if not draft.get("ready") or not dest.get("publicationId"):
                raise BridgeError("post_validation_refused")
            entry.update(status="draft", postId=draft["postId"], publicationId=dest["publicationId"], revision=draft["revision"])
            save(state)
            # Pacing advice is not a hard limit: the owner requested immediate
            # Public posting and explicitly rejected a separate TikTok schedule.
            sent = client.tool("vidiq_social_post_publish", dict(postId=entry["postId"],
                revision=entry["revision"], publicationIds=[entry["publicationId"]]))
            entry["status"] = next((d["status"] for d in sent.get("destinations", [])
                                    if d.get("publicationId") == entry["publicationId"]), "uncertain")
            save(state)
            until = time.time() + 100
            while entry["status"] in ("submitted", "inProgress") and time.time() < until:
                time.sleep(6)
                reconcile(client, entry, state, save)
            if entry["status"] == "completed":
                result["sent"] += 1
            if entry.get("failureCode") == "limitReached":
                state['vidiq_tiktok_limit_at'] = now
                save(state)
                result["errors"].append("platform_limit")
                break
        except (BridgeError, requests.RequestException, OSError, ValueError, KeyError, zipfile.BadZipFile, subprocess.SubprocessError) as exc:
            error = str(exc) if isinstance(exc, BridgeError) else type(exc).__name__
            result["errors"].append(error)
            entry.update(status="reconciliationRequired" if entry.get("status") == "reconciliationRequired" else
                         "uncertain" if entry.get("status") in ("creating","draft","submitted","inProgress") else "media_failed",
                         error=error, checked_at=now)
            save(state)
    save(state)
    return result
