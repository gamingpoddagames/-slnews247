"""Curated real Sri Lankan stock photos; no publisher-image scraping."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import requests
from PIL import Image

LICENSE = 'https://www.pexels.com/license/'
CATALOG = {
    'weather': {'id': 32160085, 'page': 'https://www.pexels.com/photo/colombo-street-view-during-rain-in-sri-lanka-32160085/', 'description': 'Rainy Colombo street; contextual stock photograph'},
    'transport': {'id': 35265473, 'page': 'https://www.pexels.com/photo/aerial-view-of-colombo-cityscape-sri-lanka-35265473/', 'description': 'Colombo city and railway; contextual stock photograph'},
    'business': {'id': 18040853, 'page': 'https://www.pexels.com/photo/skyscrapers-of-world-trade-center-colombo-sri-lanka-18040853/', 'description': 'Colombo commercial buildings; contextual stock photograph'},
    'general': {'id': 31399466, 'page': 'https://www.pexels.com/photo/colombo-skyline-with-sri-lankan-flag-31399466/', 'description': 'Sri Lankan flag and buildings; contextual stock photograph'},
}


def topic(article):
    text = article.get('title_si', '') + ' ' + article.get('summary_si', '')
    if any(word in text for word in ['කාලගුණ', 'වැසි', 'වර්ෂා', 'සුළි', 'ගංවතුර']):
        return 'weather'
    if any(word in text for word in ['දුම්රිය', 'ප්‍රවාහන', 'මාර්ග', 'බස්']):
        return 'transport'
    if any(word in text for word in ['ආර්ථික', 'බැංකු', 'ව්‍යාපාර', 'ආයෝජන', 'වෙළෙඳ', 'මුදල්']):
        return 'business'
    return 'general'


def choose_photo(article):
    asset = CATALOG[topic(article)]
    directory = Path('assets/media')
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"pexels-{asset['id']}.jpg"
    if not path.exists():
        url = f"https://images.pexels.com/photos/{asset['id']}/pexels-photo-{asset['id']}.jpeg?auto=compress&cs=tinysrgb&w=1400"
        response = requests.get(url, timeout=(5, 20))
        response.raise_for_status()
        if len(response.content) > 12_000_000:
            raise ValueError('Photo exceeds download limit')
        temp = path.with_suffix('.tmp')
        temp.write_bytes(response.content)
        try:
            with Image.open(temp) as image:
                if image.width < 700 or image.height < 700:
                    raise ValueError('Photo resolution too small')
                image.convert('RGB').save(path, 'JPEG', quality=92)
        finally:
            temp.unlink(missing_ok=True)
    manifest = Path('data/media_usage.json')
    history = json.loads(manifest.read_text()) if manifest.exists() else {}
    history[article['id']] = {**asset, 'license': LICENSE, 'visible_credit_required': False,
                              'contextual_only': True, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                              'checked_at': datetime.now(timezone.utc).isoformat()}
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(dict(list(history.items())[-500:]), ensure_ascii=False, indent=2), encoding='utf-8')
    return str(path)


def post_image(article):
    from video import create_card
    photo = choose_photo(article)
    path = Path('output') / f"post-{article['id']}.jpg"
    path.parent.mkdir(exist_ok=True)
    if not path.exists():
        create_card(article['title_si'], article['summary_si'], str(path), photo, height=1350)
    return str(path)
