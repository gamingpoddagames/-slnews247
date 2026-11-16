"""Only reviewed, licensed media of the exact story; never stock fallbacks."""
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit
import requests
from PIL import Image

REGISTRY = Path('data/verified_event_media.json')
USAGE = Path('data/event_media_usage.json')


def choose_photo(article):
    registry = json.loads(REGISTRY.read_text()) if REGISTRY.exists() else {}
    asset = registry.get(article['id'])
    if not asset:
        return None
    # A publisher thumbnail or topical resemblance is not verification or permission.
    if (asset.get('article_url') != article.get('link')
            or asset.get('verified_event') is not True
            or asset.get('rights_verified') is not True
            or asset.get('attribution_required') is not False
            or not asset.get('verification_notes')
            or not asset.get('rights_evidence')
            or not asset.get('sha256')):
        return None
    url = asset.get('url', '')
    if urlsplit(url).scheme != 'https':
        return None
    path = Path('assets/events') / (article['id'] + '.jpg')
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        response = requests.get(url, timeout=(5, 20))
        response.raise_for_status()
        content = response.content
        if len(content) > 12_000_000:
            return None
        if hashlib.sha256(content).hexdigest() != asset['sha256']:
            return None
        temp = path.with_suffix('.tmp')
        temp.write_bytes(content)
        try:
            with Image.open(temp) as image:
                image.verify()
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
