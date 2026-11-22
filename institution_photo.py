"""Vetted, correctly identified real photos of named news institutions.

Only match a named institution in the headline. This is NOT footage or a photo
of a monetary-policy meeting. Do not substitute topical stock photographs.
The source license must permit reuse and require attribution in the post.
"""
import hashlib
from io import BytesIO
from pathlib import Path

import requests
from PIL import Image

CBSL_PHOTO = {
    "url": "https://upload.wikimedia.org/wikipedia/commons/2/25/Sri_lanka2024.png",
    "sha1": "32d3dcfbd8153ce7e3e155f149dd7c166ef14b23",
    "source": "https://commons.wikimedia.org/wiki/File:Sri_lanka2024.png",
    "license_url": "https://creativecommons.org/licenses/by/4.0/",
    "creator": "Zsastaba",
    "license": "CC BY 4.0",
    "label_si": "ශ්‍රී ලංකා මහ බැංකුවේ ගොඩනැගිල්ල",
}
CBSL_NAMES = ("මහ බැංකුව", "මහබැංකුව", "central bank of sri lanka", "cbsl")


def select_institution_photo(article, session=None):
    """Return verified named-building photo with proper credit or (None, None).

    Restrict to the bank itself being named in the headline; otherwise a
    finance or other-bank news item must not get this photograph.
    """
    headline = str(article.get("title_si", "")).casefold()
    if not any(name in headline for name in CBSL_NAMES):
        return None, None
    info = CBSL_PHOTO
    session = session or requests
    response = session.get(
        info["url"],
        headers={"User-Agent": "SLNews247/1.0 (educational news; Wikimedia CC attribution)"},
        timeout=(5, 22),
    )
    response.raise_for_status()
    raw = response.content
    if not raw or len(raw) > 8_000_000:
        raise ValueError("Institution image missing or too large")
    if hashlib.sha1(raw).hexdigest() != info["sha1"]:
        raise ValueError("Institution photo bytes changed: needs rights review")
    with Image.open(BytesIO(raw)) as original:
        original.verify()
    with Image.open(BytesIO(raw)) as original:
        if original.width < 700 or original.height < 500:
            raise ValueError("Institution photo too small")
        photo = original.convert("RGB")
        output = Path("output") / "verified_cbsl_building.jpg"
        output.parent.mkdir(parents=True, exist_ok=True)
        photo.save(output, quality=94)
    credit = {
        "source": info["source"],
        "license_url": info["license_url"],
        "creator": info["creator"],
        "license": info["license"],
        "label_si": info["label_si"],
        "modified": "cropped and resized in SL News 247 news card",
    }
    return str(output), credit
