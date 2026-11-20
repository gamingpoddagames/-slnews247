"""Real-photo selection: verified exact-event media or licensed Commons context.

A publisher's public og:image is a discovery lead, NOT republication permission.
Context photos are explicitly labelled and credited, never claimed as event photos.
"""
import hashlib
import html
import json
import re
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse

import requests
from PIL import Image, UnidentifiedImageError
from bs4 import BeautifulSoup

from media import choose_photo
from visual_news import topic_for

API = "https://commons.wikimedia.org/w/api.php"
USER_AGENT = "SLNews247/1.0 (licensed contextual photo discovery; Wikimedia Commons)"
# Conservative subject-level matches only: no person/event-specific imagery.
SEARCH = {
    "religion": ["Asgiriya Maha Viharaya Kandy", "Sri Lanka Buddhist temple", "Buddhist temple Kandy"],
    "education": ["school classroom Sri Lanka", "school classroom"],
    "weather": ["rain clouds Sri Lanka", "monsoon clouds"],
    "health": ["hospital building Sri Lanka", "hospital building"],
    "transport": ["road Sri Lanka", "railway Sri Lanka"],
    "economy": ["Sri Lanka market", "market stalls"],
    "sport": ["cricket stadium Sri Lanka", "cricket ground"],
    "government": ["Parliament of Sri Lanka building"],
    "energy": ["electric power transmission Sri Lanka", "power lines"],
}
PERMITTED = {"cc0", "public domain", "cc-by-4.0", "cc-by-3.0", "cc-by-sa-4.0",
             "cc-by-sa-3.0", "cc-by-2.0", "cc-by-sa-2.0"}
MAX_BYTES = 10_000_000


def plain(value):
    return BeautifulSoup(html.unescape(str(value or "")), "html.parser").get_text(" ", strip=True)


def permitted(info):
    meta = info.get("extmetadata", {})
    license_name = plain(meta.get("LicenseShortName", {}).get("value", "")).lower()
    normalized = re.sub(r"[^a-z0-9]", "", license_name)
    allowed = {re.sub(r"[^a-z0-9]", "", name) for name in PERMITTED}
    if normalized.startswith("pd") or normalized == "publicdomain":
        return True
    if normalized not in allowed:
        return False
    restrictions = plain(meta.get("Restrictions", {}).get("value", ""))
    return not restrictions


def _metadata_search(term, session):
    response = session.get(API, params={
        "action": "query", "generator": "search", "gsrsearch": term + " filetype:bitmap",
        "gsrnamespace": 6, "gsrlimit": 8, "prop": "imageinfo",
        "iiprop": "url|size|extmetadata", "iiurlwidth": 1200, "format": "json",
    }, headers={"User-Agent": USER_AGENT}, timeout=(5, 12))
    response.raise_for_status()
    return response.json().get("query", {}).get("pages", {}).values()


def discover_licensed_photo(article, session=None):
    """Find one real, permissively licensed, topic-relevant contextual photograph.

    Return (local_file, credit) or (None, None). Never fall back to arbitrary
    publisher images, illustrations, unverified event claims or copyrighted logos.
    """
    category = topic_for(article)
    if category not in SEARCH:
        return None, None
    session = session or requests.Session()
    for term in SEARCH[category]:
        try:
            pages = _metadata_search(term, session)
        except (requests.RequestException, ValueError):
            continue
        for page in pages:
            title = page.get("title", "")
            info = (page.get("imageinfo") or [{}])[0]
            url = info.get("thumburl") or info.get("url", "")
            source = info.get("descriptionurl", "")
            if not permitted(info) or not title.startswith("File:"):
                continue
            if not urlparse(url).hostname or not urlparse(url).hostname.endswith(".wikimedia.org"):
                continue
            if not source.startswith("https://commons.wikimedia.org/wiki/"):
                continue
            if int(info.get("width", 0)) < 750 or int(info.get("height", 0)) < 500:
                continue
            # Avoid likely drawings and infographics; require photo-shaped source files.
            if not re.search(r"\.(?:jpg|jpeg|webp)$", title, re.I):
                continue
            creator = plain(info.get("extmetadata", {}).get("Artist", {}).get("value", ""))[:180]
            license_text = plain(info.get("extmetadata", {}).get("LicenseShortName", {}).get("value", ""))
            license_url = plain(info.get("extmetadata", {}).get("LicenseUrl", {}).get("value", ""))
            if not creator and not license_text.lower().startswith(("cc0", "pd-", "public domain")):
                continue
            try:
                response = session.get(url, headers={"User-Agent": USER_AGENT},
                                       timeout=(5, 20), stream=True)
                response.raise_for_status()
                size = 0
                data = bytearray()
                for chunk in response.iter_content(65536):
                    size += len(chunk)
                    if size > MAX_BYTES:
                        raise ValueError("Image exceeds maximum bytes")
                    data.extend(chunk)
                with Image.open(BytesIO(data)) as img:
                    img.verify()
                with Image.open(BytesIO(data)) as img:
                    if img.width < 700 or img.height < 450:
                        continue
                    rgb = img.convert("RGB")
                    identifier = re.sub(r"[^A-Za-z0-9_-]", "", str(article.get("id", "")))[:60]
                    identifier = identifier or hashlib.sha256(str(article["title_si"]).encode()).hexdigest()[:16]
                    path = Path("output") / ("licensed_photo_" + identifier + ".jpg")
                    path.parent.mkdir(parents=True, exist_ok=True)
                    rgb.save(path, quality=90)
                credit = {"source": source, "creator": creator or "Wikimedia Commons contributor",
                          "license": license_text, "license_url": license_url,
                          "kind": "contextual_not_event", "file_title": title}
                Path(str(path) + ".credit.json").write_text(
                    json.dumps(credit, ensure_ascii=False), encoding="utf-8")
                return str(path), credit
            except (requests.RequestException, ValueError, OSError, UnidentifiedImageError):
                continue
    return None, None


def select_real_photo(article):
    """Return only a licensed, reviewed photograph of this *exact* news event.

    Topic-related archive photos, Commons keyword results and generated images
    are never substitutes for a verified photo of the named incident.
    """
    try:
        photo = choose_photo(article)
    except (requests.RequestException, OSError, ValueError, KeyError) as exc:
        print("Verified exact-event photo unavailable:", type(exc).__name__)
        return None, None, None
    if photo:
        return photo, "verified_event_photo", None
    return None, None, None
