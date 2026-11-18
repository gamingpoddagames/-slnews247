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
    # First use a preapproved direct exact-event file with verified bytes.
    direct = choose_media(article, 'video')
    if direct:
        return direct
    registry = json.loads(REGISTRY.read_text()) if REGISTRY.exists() else {}
    asset = registry.get(article['id'], {}).get('video', {})
    if not isinstance(asset, dict) or not asset.get('youtube_url'):
        return None
    from authorized_youtube import download_approved_youtube
    return download_approved_youtube(article, asset)


# Curated license-checked contextual example; it is NOT the construction site
# of the Ruwanpura Expressway. CC0 source:
# https://commons.wikimedia.org/wiki/File:Galle.to_Matara_Highway.jpg
ILLUSTRATIVE_PHOTOS = {
    'sri_lanka_expressway_cc0': (
        'https://upload.wikimedia.org/wikipedia/commons/1/16/Galle.to_Matara_Highway.jpg',
        'https://commons.wikimedia.org/wiki/File:Galle.to_Matara_Highway.jpg',
    ),
}


def post_image(article):
    """Prefer licensed exact-event imagery, then clearly labelled CC0 context."""
    photo = choose_photo(article)
    if photo:
        from image import news_card
        return news_card(article, image_path=photo)
    key = article.get('illustrative_photo')
    if key not in ILLUSTRATIVE_PHOTOS:
        return None
    from image import news_card, download_image
    url, source_page = ILLUSTRATIVE_PHOTOS[key]
    path = Path('assets/illustrative') / (key + '.jpg')
    if not path.is_file():
        path.parent.mkdir(parents=True, exist_ok=True)
        if not download_image(url, str(path)):
            return None
    return news_card(article, image_path=str(path), illustrative=True)
