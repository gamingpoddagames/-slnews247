"""Only reviewed, licensed media of the exact story; never stock fallbacks."""
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit
import requests
from PIL import Image

REGISTRY = Path('data/verified_event_media.json')
USAGE = Path('data/event_media_usage.json')


def choose_media(article, kind):
    registry = json.loads(REGISTRY.read_text()) if REGISTRY.exists() else {}
    entry = registry.get(article['id'], {})
    asset = entry.get(kind) if kind in entry else (entry if kind == 'photo' else None)
    if not asset:
        return None
    # A publisher thumbnail or topical resemblance is not verification or permission.
    if (asset.get('article_url') != article.get('link')
            or asset.get('verified_event') is not True
            or asset.get('rights_verified') is not True
            or asset.get('attribution_required') is not False
            or not asset.get('verification_notes')
            or not asset.get('rights_evidence')
            or not asset.get('sha256')
            or (kind == 'video' and asset.get('real_footage_verified') is not True)):
        return None
    url = asset.get('url', '')
    if urlsplit(url).scheme != 'https':
        return None
    path = Path('assets/events') / (article['id'] + ('.mp4' if kind == 'video' else '.jpg'))
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        response = requests.get(url, timeout=(5, 20))
        response.raise_for_status()
        content = response.content
        if len(content) > (60_000_000 if kind == 'video' else 12_000_000):
            return None
        if hashlib.sha256(content).hexdigest() != asset['sha256']:
            return None
        temp = path.with_suffix('.tmp')
        temp.write_bytes(content)
        try:
            if kind == 'photo':
                with Image.open(temp) as image:
                    image.verify()
            else:
                from video import probe_footage
                probe_footage(str(temp))
            temp.replace(path)
        finally:
            temp.unlink(missing_ok=True)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != asset['sha256']:
        return None
    usage = json.loads(USAGE.read_text()) if USAGE.exists() else {}
    if digest in usage and usage[digest]['article_id'] != article['id']:
        return None
    usage[digest] = {'article_id': article['id'], 'article_url': article['link'],
                     'rights_evidence': asset['rights_evidence']}
    USAGE.parent.mkdir(parents=True, exist_ok=True)
    temp = USAGE.with_suffix('.tmp')
    temp.write_text(json.dumps(usage, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(USAGE)
    return str(path)


def choose_photo(article):
    return choose_media(article, 'photo')


def choose_video(article):
    return choose_media(article, 'video')


def post_image(article):
    photo = choose_photo(article)
    if not photo:
        return None
    from video import create_card
    path = Path('output') / f"post-{article['id']}.jpg"
    path.parent.mkdir(exist_ok=True)
    create_card(article['title_si'], article['summary_si'], str(path), photo,
                height=1350, contextual=False)
    return str(path)
