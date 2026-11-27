"""Licensed subject photographs for stories without reusable exact-event media.

Use concrete subjects mentioned by the story, not unrelated incident photographs.
Pexels stock and Commons archive images remain visibly identified as context.
"""
import hashlib
import json
import os
import re
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from urllib.parse import urlsplit

import requests
from PIL import Image

# Sinhala triggers, a narrow English query, acceptable caption subjects, label.
RULES = (
    (('යුද අභ්‍යාස', 'යුද්ධ අභ්‍යාස', 'මිත්‍ර ශක්ති'), 'Sri Lanka flag', ('sri lanka flag', 'sri lankan flag', 'flag of sri lanka'), 'ශ්‍රී ලංකාව'),
    (('ණය ශ්‍රේණිගත', 'ණය ප්‍රතිව්‍යුහගත'), 'financial report chart', ('financial chart', 'financial report', 'financial graph', 'stock market'), 'ආර්ථිකය'),
    (('වැය ශීර්ෂ', 'අයවැය'), 'budget calculator documents', ('calculator', 'budget', 'financial report'), 'අයවැය'),
    (('ආදායම', 'වැටුප්', 'පඩි වැඩි'), 'money coins calculator', ('coins', 'banknotes', 'calculator', 'money'), 'ආදායම'),
    (('සංඝ සම්මේල', 'සංඝ සමුළු', 'බෞද්ධ සංඝ', 'බෞද්ධ සමුළු'), 'Buddha statue Buddhist temple', ('buddha statue', 'buddhist statue', 'buddhist temple'), 'බෞද්ධ පුවත'),
    (('පාසල් නිවාඩු', 'පාසල් වාර', 'පාසල් විභාග', 'අධ්‍යාපන ප්‍රතිපත්ති'), 'empty classroom school', ('empty classroom', 'classroom', 'school building'), 'පාසල්'),
    (('වෘත්තීය පුහුණුව', 'වෘත්තීය අධ්‍යාපන'), 'vocational training workshop tools', ('workshop', 'tools', 'training', 'welding', 'carpentry'), 'වෘත්තීය පුහුණුව'),
    (('මැතිසබ', 'පාර්ලිමේන්තු'), 'Sri Lanka Parliament building', ('parliament',), 'පාර්ලිමේන්තු පුවත'),
    (('ක්‍රිකට්', 'ක්රිකට්'), 'cricket bat ball pitch', ('cricket',), 'ක්‍රිකට්'),
    (('කාලගුණ', 'වැසි', 'වර්ෂාව'), 'rain clouds rainfall', ('rain', 'rainfall', 'storm clouds'), 'කාලගුණය'),
    (('මුහුද', 'මුහුදු', 'සුළං', 'සුලං'), 'ocean waves wind', ('ocean waves', 'sea waves', 'rough sea'), 'මුහුදු කාලගුණය'),
    (('එළවළු', 'එලවළු'), 'fresh vegetables market', ('vegetables',), 'එළවළු'),
    (('තේ අපනයන', 'තේ මිල', 'තේ නිෂ්පාදන'), 'tea plantation tea leaves', ('tea leaves', 'tea plantation', 'tea field'), 'තේ නිෂ්පාදනය'),
    (('ඉන්ධන මිල', 'ඉන්ධන සැපයුම', 'පෙට්‍රල්'), 'fuel pump petrol station', ('fuel', 'gas station', 'petrol'), 'ඉන්ධන'),
    (('විදුලි බිල', 'විදුලි ගාස්තු', 'විදුලි සැපයුම'), 'electric power transmission tower', ('power line', 'transmission', 'electricity'), 'විදුලි සැපයුම'),
    (('රන් මිල', 'රත්‍රන් මිල'), 'gold bars bullion', ('gold bar', 'bullion', 'gold bars'), 'රන් මිල'),
    (('සහල් මිල', 'සහල් ආනයන', 'වී මිල'), 'uncooked rice grains', ('rice grains', 'uncooked rice', 'raw rice'), 'සහල්'),
    (('දුම්රිය සේවා', 'දුම්රිය ගාස්තු', 'දුම්රිය ධාවන'), 'railway tracks train', ('railway', 'train tracks', 'railroad'), 'දුම්රිය සේවා'),
    (('කොටස් වෙළෙඳපොළ', 'කොටස් වෙළඳපොළ'), 'stock market financial chart screen', ('stock market', 'stock trading', 'financial chart'), 'කොටස් වෙළෙඳපොළ'),
)
SENSITIVE = ('මරණ', 'ඝාත', 'අනතුර', 'ප්‍රහාර', 'අත්අඩංගු', 'අල්ලයි', 'සැකකරු', 'අතවර', 'අපරාධ', 'තුවාල', 'සුළි කුණාටු', 'විපත', 'ගංවතුර', 'ගිනි', 'වංචා')
MAX_BYTES = 10_000_000
COMMONS_LICENSES = re.compile(
    r'https://creativecommons\.org/(?:licenses/by/(?:2\.0|3\.0|4\.0)|publicdomain/(?:zero|mark)/1\.0)/?')
UNSAFE_CAPTIONS = ('portrait', 'selfie', 'close up of a face', 'protest', 'riot', 'funeral', 'crash', 'injured', 'dead body')


def _trigger_matches(text, trigger):
    # "ආදායම" (income) must not accidentally match "ආදායම් බදු"
    # (income tax), a different subject requiring its own reviewed rule.
    if trigger == 'ආදායම':
        return bool(re.search(r'(?<![\u0d80-\u0dff])ආදායම(?![\u0d80-\u0dff])', text))
    return trigger in text


def rule_for(title, summary=''):
    title = str(title or '')
    if (any(w in title for w in SENSITIVE)
            or re.search(r'(?<![\u0d80-\u0dff])මරු', title)):
        return None
    # Prefer the headline's explicit subject; consult the actual story summary
    # for headlines such as "වැය ශීර්ෂ සම්මතයි". Never infer from an ID.
    for text in (title, str(summary or '')):
        match = next((r for r in RULES if any(_trigger_matches(text, w) for w in r[0])), None)
        if match:
            return match
    return None


def _caption_matches(caption, rule):
    text = re.sub(r'[-_]+', ' ', str(caption or '')).casefold()
    if any(w in text for w in UNSAFE_CAPTIONS):
        return False
    if not any(re.search(r'\b' + re.escape(term) + r'\b', text) for term in rule[2]):
        return False
    # An overseas parliament/flag is not a photograph of the Sri Lankan one.
    if rule[1].startswith('Sri Lanka '):
        return bool(re.search(r'\bsri lanka(?:n)?\b', text))
    return True


def _download_photo(url, article_id, credit, host):
    if urlsplit(url).scheme != 'https' or urlsplit(url).hostname != host:
        return None
    path = Path('output') / ('subject_' + hashlib.sha256(
        (str(article_id) + url).encode()).hexdigest()[:24] + '.jpg')
    try:
        if not path.is_file():
            data = bytearray()
            with requests.get(url, stream=True, allow_redirects=False, timeout=(4, 12)) as response:
                if response.status_code != 200:
                    return None
                for chunk in response.iter_content(65536):
                    data.extend(chunk)
                    if len(data) > MAX_BYTES:
                        raise ValueError('Photo exceeds size limit')
            with Image.open(BytesIO(data)) as image:
                image.verify()
            with Image.open(BytesIO(data)) as image:
                if image.width < 600 or image.height < 400:
                    return None
                path.parent.mkdir(parents=True, exist_ok=True)
                image.convert('RGB').save(path, quality=90)
        # Keep the source, licence and context evidence with the rendered assets.
        evidence = dict(credit, article_id=str(article_id), media_url=url,
                        usage='subject_context_not_exact_event',
                        sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        Path(str(path) + '.credit.json').write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2), encoding='utf-8')
        return str(path), 'licensed_subject_stock', credit
    except (requests.RequestException, OSError, ValueError, TypeError):
        return None


def _pexels_photos(rule, article_id, key):
    try:
        response = requests.get('https://api.pexels.com/v1/search',
            headers={'Authorization': key},
            params={'query': rule[1], 'per_page': 15, 'orientation': 'landscape'},
            timeout=(4, 10))
        response.raise_for_status()
        items = response.json().get('photos', [])
    except (requests.RequestException, ValueError, TypeError):
        return ()
    output = []
    for item in items:
        caption = str(item.get('alt') or '')
        if not _caption_matches(caption, rule):
            continue
        source = item.get('url') or ''
        parsed = urlsplit(source)
        if parsed.scheme != 'https' or parsed.hostname != 'www.pexels.com' or not parsed.path.startswith('/photo/'):
            continue
        creator = str(item.get('photographer') or '').strip()[:100]
        if not creator:
            continue
        credit = {'creator': creator, 'source': source, 'provider': 'Pexels',
                  'license': 'Pexels License', 'license_url': 'https://www.pexels.com/license/',
                  'label_si': 'Stock photo', 'subject_query': rule[1], 'subject_evidence': caption}
        photo = _download_photo((item.get('src') or {}).get('large') or '',
                                article_id, credit, 'images.pexels.com')
        if photo:
            output.append(photo)
        if len(output) >= 3:
            break
    return tuple(output)


def _commons_photos(rule, article_id):
    # This is a subject-specific search, not the old broad topic fallback.
    from real_photo import _metadata_search, permitted, plain
    try:
        pages = _metadata_search(rule[1], requests.Session())
    except (requests.RequestException, ValueError, TypeError):
        return ()
    output = []
    for page in pages:
        title = str(page.get('title') or '')
        info = (page.get('imageinfo') or [{}])[0]
        meta = info.get('extmetadata') or {}
        caption = title + ' ' + plain(meta.get('ImageDescription', {}).get('value', ''))
        if not title.lower().endswith(('.jpg', '.jpeg', '.webp')) or not _caption_matches(caption, rule):
            continue
        license_url = plain(meta.get('LicenseUrl', {}).get('value', ''))
        if (not permitted(info) or plain(meta.get('Restrictions', {}).get('value', ''))
                or not COMMONS_LICENSES.fullmatch(license_url)):
            continue
        source = info.get('descriptionurl') or ''
        parsed = urlsplit(source)
        creator = plain(meta.get('Artist', {}).get('value', ''))[:180]
        if (parsed.scheme != 'https' or parsed.hostname != 'commons.wikimedia.org'
                or not parsed.path.startswith('/wiki/File:') or not creator):
            continue
        credit = {'creator': creator, 'source': source, 'provider': 'Wikimedia Commons',
                  'license': plain(meta.get('LicenseShortName', {}).get('value', '')),
                  'license_url': license_url, 'label_si': 'Archive photo',
                  'subject_query': rule[1], 'subject_evidence': caption}
        photo = _download_photo(info.get('thumburl') or info.get('url') or '',
                                article_id, credit, 'upload.wikimedia.org')
        if photo:
            output.append(photo)
        if len(output) >= 3:
            break
    return tuple(output)


@lru_cache(maxsize=64)
def subject_photo_set(title, article_id, summary=''):
    rule = rule_for(title, summary)
    if not rule:
        return ()
    key = os.getenv('PEXELS_API_KEY', '').strip()
    photos = _pexels_photos(rule, article_id, key) if key else ()
    if photos:
        return photos
    # A missing key, failed request or irrelevant result must not disable
    # another licensed provider. No arbitrary publisher image is substituted.
    return _commons_photos(rule, article_id)

