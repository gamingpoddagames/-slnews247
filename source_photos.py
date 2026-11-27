"""Article-linked photographs with an explicit reusable image licence.

Publisher thumbnails and RSS images are leads, not reuse permission.
Only a matching article's explicitly licensed image objects qualify here.
"""
import hashlib
import json
import re
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from urllib.parse import urlsplit, urljoin

import requests
from bs4 import BeautifulSoup
from PIL import Image

MAX_BYTES = 10_000_000
ALLOWED_LICENSE = re.compile(r'https://creativecommons\.org/(?:licenses/(?:by|by-sa)/(?:2\.0|3\.0|4\.0)|publicdomain/zero/1\.0)/?')


def _normal(value):
    return re.sub(r'[\W_]+', '', str(value or ''), flags=re.UNICODE).casefold()


def _nodes(obj):
    if isinstance(obj, dict):
        yield obj
        for key in ('@graph', 'mainEntity'):
            yield from _nodes(obj.get(key))
    elif isinstance(obj, list):
        for item in obj:
            yield from _nodes(item)


def _creator(value):
    if isinstance(value, dict):
        value = value.get('name')
    return str(value or '').strip()[:150] if isinstance(value, str) else ''


def licensed_candidates(html, link, headline):
    soup = BeautifulSoup(html, 'html.parser')
    results = []
    seen = set()
    for tag in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(tag.string or tag.get_text())
        except (TypeError, ValueError):
            continue
        for node in _nodes(data):
            types = node.get('@type', [])
            if isinstance(types, str):
                types = [types]
            if not any(t in types for t in ('NewsArticle', 'Article', 'ReportageNewsArticle')):
                continue
            if _normal(node.get('headline')) != _normal(headline):
                continue
            images = node.get('image', [])
            if not isinstance(images, list):
                images = [images]
            for item in images:
                if not isinstance(item, dict) or item.get('@type') != 'ImageObject':
                    continue
                license_url = item.get('license', '')
                if not isinstance(license_url, str) or not ALLOWED_LICENSE.fullmatch(license_url):
                    continue
                creator = _creator(item.get('creator') or item.get('creditText'))
                raw_url = item.get('contentUrl') or item.get('url') or ''
                if not isinstance(raw_url, str) or not raw_url or not creator:
                    continue
                url = urljoin(link, raw_url)
                target = urlsplit(url)
                if target.scheme != 'https' or target.hostname != urlsplit(link).hostname:
                    continue
                if url in seen or re.search(r'logo|placeholder|default[-_]?image|avatar', target.path, re.I):
                    continue
                seen.add(url)
                results.append({'url': url, 'creator': creator, 'license_url': license_url,
                    'license': license_url.removeprefix('https://creativecommons.org/').strip('/'),
                    'source': link, 'label_si': 'පුවතට අදාළ ඡායාරූපය'})
                if len(results) >= 3:
                    return results
    return results


@lru_cache(maxsize=64)
def source_photo_set(link, headline):
    from publisher_videos import HOSTS
    parsed = urlsplit(link)
    if parsed.scheme != 'https' or parsed.hostname not in HOSTS or not headline:
        return ()
    try:
        response = requests.get(link, timeout=(4, 7), allow_redirects=False)
        if response.status_code != 200:
            return ()
        candidates = licensed_candidates(response.content, link, headline)
    except (requests.RequestException, ValueError, TypeError):
        return ()
    output = []
    for credit in candidates:
        try:
            response = requests.get(credit['url'], timeout=(4, 10), stream=True, allow_redirects=False)
            if response.status_code != 200:
                continue
            data = bytearray()
            with response:
                for chunk in response.iter_content(65536):
                    data.extend(chunk)
                    if len(data) > MAX_BYTES:
                        raise ValueError('Photo exceeds size limit')
            with Image.open(BytesIO(data)) as photo:
                photo.verify()
            with Image.open(BytesIO(data)) as photo:
                if photo.width < 600 or photo.height < 400:
                    continue
                path = Path('output') / ('source_' + hashlib.sha256(bytes(data)).hexdigest()[:24] + '.jpg')
                path.parent.mkdir(parents=True, exist_ok=True)
                photo.convert('RGB').save(path, quality=90)
            if not any(str(path) == old[0] for old in output):
                output.append((str(path), 'licensed_article_photo', credit))
        except (requests.RequestException, ValueError, OSError):
            continue
    return tuple(output)
