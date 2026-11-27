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


def select_subject_photo(article):
    title = article.get('title_si', '')
    if not any(w in title for w in ('මිල', 'අපනයන', 'ආදායම')):
        return None
    if any(w in title for w in ('ගිනි', 'මරණ', 'විෂ', 'අනතුර', 'විරෝධ', 'අත්අඩංගු')):
        return None
    term = next((e for s, e in [('එළවළු', 'vegetables'), ('තැඹිලි', 'king coconut')] if s in title), None)
    if not term:
        return None
    session = requests.Session()
    for page in _metadata_search('intitle:"' + term + '"', session):
        info = (page.get('imageinfo') or [{}])[0]
        meta = info.get('extmetadata', {})
        licence = re.sub(r'[^a-z0-9]', '', plain(meta.get('LicenseShortName', {}).get('value')).lower())
        if licence not in ('cc0', 'cc010', 'publicdomain', 'pdself', 'pdold'):
            continue
        if plain(meta.get('Restrictions', {}).get('value')) or term not in page.get('title', '').lower():
            continue
        url = info.get('thumburl') or info.get('url', '')
        if urlparse(url).scheme != 'https' or urlparse(url).hostname != 'upload.wikimedia.org':
            continue
        if not page.get('title', '').lower().endswith(('.jpg', '.jpeg', '.webp')):
            continue
        response = session.get(url, timeout=(5, 12), stream=True)
        response.raise_for_status()
        data = bytearray()
        for chunk in response.iter_content(65536):
            data.extend(chunk)
            if len(data) > MAX_BYTES:
                raise ValueError('Subject photo too large')
        with Image.open(BytesIO(data)) as img:
            img.verify()
        with Image.open(BytesIO(data)) as img:
            if img.width < 700 or img.height < 450:
                continue
            path = Path('output') / ('subject_' + hashlib.sha256(article['id'].encode()).hexdigest()[:24] + '.jpg')
            path.parent.mkdir(parents=True, exist_ok=True)
            img.convert('RGB').save(path, quality=90)
        Path(str(path) + '.credit.json').write_text(json.dumps({
            'source': info.get('descriptionurl'), 'license': licence,
            'kind': 'neutral_subject_not_event'}, ensure_ascii=False), encoding='utf-8')
        return str(path)
    return None


def select_event_video_frame(article):
    """Use a still only from the exact-event clip already approved by media.py."""
    import subprocess
    from media import choose_video
    clip = choose_video(article)
    if not clip:
        return None
    output = Path('output') / ('event_frame_' + hashlib.sha256(
        str(article['id']).encode()).hexdigest()[:24] + '.jpg')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.unlink(missing_ok=True)
    subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', str(clip),
                    '-t', '2', '-vf', 'thumbnail=30,scale=1280:-2',
                    '-frames:v', '1', str(output)],
                   check=True, timeout=35, capture_output=True)
    with Image.open(output) as image:
        image.verify()
    return str(output)



# Named landmarks in the headline only; never substitute incident photography.
NAMED_SUBJECTS = (
    (('කටුනායක ගුවන්තොටුපළ', 'කටුනායක ගුවන් තොටුපළ'), 'Bandaranaike International Airport', ('bandaranaike', 'airport'), 'කටුනායක ගුවන්තොටුපළ'),
    (('කොළඹ වරාය',), 'Port of Colombo', ('colombo', 'port'), 'කොළඹ වරාය'),
    (('දළදා මාලිගාව', 'දළදා මාළිගාව'), 'Temple of the Tooth Kandy', ('temple', 'tooth'), 'දළදා මාලිගාව'),
    (('නෙළුම් කුලුන', 'නෙළුම් කුළුණ'), 'Colombo Lotus Tower', ('lotus', 'tower'), 'නෙළුම් කුලුන'),
    (('පාර්ලිමේන්තුව', 'පාර්ලිමේන්තු'), 'Sri Lanka Parliament building', ('parliament', 'sri lanka'), 'ශ්‍රී ලංකා පාර්ලිමේන්තුව'),
    (('කොළඹ කොටස් වෙළෙඳපොළ', 'කොළඹ කොටස් වෙළඳපොළ'), 'Colombo Stock Exchange', ('colombo', 'stock exchange'), 'කොළඹ කොටස් වෙළෙඳපොළ'),
    (('ශ්‍රී ලංකා ක්‍රිකට් කණ්ඩායම', 'ශ්‍රී ලංකා ක්‍රිකට් කණ්ඩායමේ'), 'Sri Lanka national cricket team', ('sri lanka', 'cricket', 'team'), 'ශ්‍රී ලංකා ක්‍රිකට් කණ්ඩායම'),
    (('කොළඹ ජාතික රෝහල',), 'National Hospital of Sri Lanka Colombo', ('national hospital', 'sri lanka'), 'කොළඹ ජාතික රෝහල'),
    (('කැලණිය විශ්වවිද්‍යාලය', 'කැලණිය විශ්වවිද්‍යාලයේ'), 'University of Kelaniya', ('university', 'kelaniya'), 'කැලණිය විශ්වවිද්‍යාලය'),
    (('පේරාදෙණිය විශ්වවිද්‍යාලය', 'පේරාදෙණිය විශ්වවිද්‍යාලයේ'), 'University of Peradeniya', ('university', 'peradeniya'), 'පේරාදෙණිය විශ්වවිද්‍යාලය'),
)

def select_named_subject_photo(article, session=None):
    title = article.get('title_si', '')
    if any(word in title for word in ('මරණ', 'මරු', 'ඝාත', 'අනතුර', 'ප්‍රහාර', 'ගිනි', 'අත්අඩංගු', 'අල්ලයි', 'සැකකරු')):
        return None, None
    rule = next((r for r in NAMED_SUBJECTS if any(w in title for w in r[0])), None)
    if not rule:
        return None, None
    _, term, tokens, label = rule
    session = session or requests.Session()
    for page in _metadata_search(term, session):
        name = page.get('title', '').lower().replace('_', ' ')
        info = (page.get('imageinfo') or [{}])[0]
        if not all(t in name for t in tokens) or not name.endswith(('.jpg', '.jpeg', '.webp')):
            continue
        if not permitted(info) or int(info.get('width', 0)) < 750 or int(info.get('height', 0)) < 500:
            continue
        url = info.get('thumburl') or info.get('url', '')
        source = info.get('descriptionurl', '')
        if urlparse(url).scheme != 'https' or urlparse(url).hostname != 'upload.wikimedia.org' or not source.startswith('https://commons.wikimedia.org/wiki/'):
            continue
        meta = info.get('extmetadata', {})
        creator = plain(meta.get('Artist', {}).get('value', ''))
        license_text = plain(meta.get('LicenseShortName', {}).get('value', ''))
        license_url = plain(meta.get('LicenseUrl', {}).get('value', ''))
        if not creator or not license_url or plain(meta.get('Restrictions', {}).get('value', '')):
            continue
        credit = {'creator': creator, 'license': license_text, 'license_url': license_url,
                  'source': source, 'label_si': label + ' - පැරණි ඡායාරූපයක්', 'kind': 'named_subject_not_event'}
        path = Path('output') / ('named_' + hashlib.sha256(source.encode()).hexdigest()[:24] + '.jpg')
        if not path.is_file():
            response = session.get(url, headers={'User-Agent': USER_AGENT}, timeout=(5, 15), stream=True)
            response.raise_for_status()
            data = bytearray()
            for chunk in response.iter_content(65536):
                data.extend(chunk)
                if len(data) > MAX_BYTES:
                    raise ValueError('Named subject photo too large')
            with Image.open(BytesIO(data)) as im:
                im.verify()
            with Image.open(BytesIO(data)) as im:
                if im.width < 700 or im.height < 450:
                    continue
                path.parent.mkdir(parents=True, exist_ok=True)
                im.convert('RGB').save(path, quality=90)
        return str(path), credit
    return None, None


def _select_real_photo(article):
    """Use real exact-event photography, then a verified *named institution*.

    A photograph of the actual Central Bank building can illustrate policy
    news ABOUT the Central Bank; it must be labelled as building/archive
    photography, never as a picture of the meeting or participants.
    Arbitrary topic-based stock photos remain forbidden.
    """
    try:
        photo = choose_photo(article)
    except (requests.RequestException, OSError, ValueError, KeyError) as exc:
        print("Verified exact-event photo unavailable:", type(exc).__name__)
        photo = None
    if photo:
        return photo, "verified_event_photo", None

    try:
        frame = select_event_video_frame(article)
        if frame:
            return frame, 'verified_event_video_frame', None
    except Exception as exc:
        # A failed clip decode never substitutes an unrelated image.
        print('Approved event frame unavailable:', type(exc).__name__)

    import os
    if os.getenv('NEWS_REQUIRE_REAL_MEDIA', 'false').lower() == 'true':
        from source_photos import source_photo_set
        photos = source_photo_set(article.get('link', ''), article.get('title_si', ''))
        if photos:
            return photos[0]

    try:
        subject = select_subject_photo(article)
        if subject:
            return subject, "licensed_subject_photo", None
    except (requests.RequestException, OSError, ValueError, KeyError):
        pass

    from institution_photo import select_institution_photo
    try:
        institutional, credit = select_institution_photo(article)
        if institutional:
            return institutional, "verified_institution_photo", credit
    except (requests.RequestException, OSError, ValueError) as exc:
        print("Verified institution photo unavailable:", type(exc).__name__)

    # Classroom archive photo only for teacher/principal labour and policy
    # news. No image is ever claimed to depict that union announcement.
    from education_photo import select_education_photo
    try:
        classroom, credit = select_education_photo(article)
        if classroom:
            return classroom, "verified_education_context_photo", credit
    except (requests.RequestException, OSError, ValueError) as exc:
        print("Vetted classroom archive photo unavailable:", type(exc).__name__)
    try:
        named, credit = select_named_subject_photo(article)
        if named:
            return named, 'verified_named_subject_photo', credit
    except (requests.RequestException, OSError, ValueError, KeyError):
        pass
    return None, None, None



# Cache one selection per exact article during each scan, so Facebook, Telegram,
# reel scenes and licence credit refer to the same downloaded asset.
_SCAN_PHOTOS = {}


def select_real_photo(article):
    import os
    if os.getenv('NEWS_REQUIRE_REAL_MEDIA', 'false').lower() != 'true':
        return _select_real_photo(article)
    key = (article.get('id'), article.get('link'), article.get('title_si'))
    if key not in _SCAN_PHOTOS:
        _SCAN_PHOTOS[key] = _select_real_photo(article)
    return _SCAN_PHOTOS[key]


def reel_photo_set(article):
    """Use multiple licensed images from the same exact article where available."""
    first = select_real_photo(article)
    if not first[0]:
        return []
    if first[1] == 'licensed_article_photo':
        from source_photos import source_photo_set
        return list(source_photo_set(article.get('link', ''), article.get('title_si', ''))) or [first]
    return [first]
