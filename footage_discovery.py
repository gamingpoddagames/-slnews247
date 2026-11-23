"""Discover exact-article video candidates from RSS and embedded publisher players.

Discovery is not authorization. No broadcaster files are downloaded or copied
until the exact-event rights registry approves reuse and verifies a file hash.
"""
import json
import re
from pathlib import Path

def discover_candidates(articles, limit=3, output_path='output/footage_candidates.json', finder=None):
    inspect_photos = finder is None
    if finder is None:
        from publisher_videos import discover_video
        finder = discover_video
    results = []
    examined = 0
    for article in articles:
        rss_urls = article.get('rss_video_urls', [])
        video_label = re.search(r'video|වීඩියෝ', article.get('title_si', ''), re.I)
        if not (rss_urls or video_label):
            continue
        if examined >= limit:
            break
        examined += 1
        for url in rss_urls[:5]:
            results.append({
                'article_id': article.get('id'), 'title': article.get('title_si'),
                'article_url': article.get('link'), 'video_url': url,
                'source': 'rss_video_enclosure', 'status': 'rights_verification_required',
                'may_download_or_publish': False})
        # Embedded player discovery is a secondary lead, not downloadable footage.
        if video_label:
            try:
                found = finder(article)
            except Exception as exc:
                results.append({
                    'article_id': article.get('id'), 'article_url': article.get('link'),
                    'source': 'publisher_page', 'status': 'discovery_unavailable',
                    'error': type(exc).__name__})
                continue
            if found:
                results.append({
                    'article_id': article.get('id'), 'title': article.get('title_si'),
                    'article_url': article.get('link'), 'player_url': found,
                    'source': 'publisher_page', 'status': 'rights_verification_required',
                    'may_download_or_publish': False})
    photos = {'status': 'not_requested'}
    if inspect_photos:
        try:
            photos = discover_article_photos(articles, limit=limit)
        except Exception as exc:
            photos = {'status': 'unavailable', 'error': type(exc).__name__}
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    return {'examined': examined, 'candidates': len(results),
            'rss_direct_candidates': sum(x.get('source') == 'rss_video_enclosure'
                                         for x in results),
            'rights_approved': 0, 'photos': photos, 'report_file': str(output)}


def discover_article_photos(articles, limit=3, output_path='output/photo_candidates.json', fetcher=None):
    """Inspect exact publisher pages for image leads, never approve reuse."""
    from urllib.parse import urlsplit, urljoin
    from bs4 import BeautifulSoup
    from publisher_videos import HOSTS
    import requests
    fetcher = fetcher or requests.get
    results = []
    examined = 0
    for article in articles:
        link = article.get('link', '')
        if urlsplit(link).scheme != 'https' or urlsplit(link).hostname not in HOSTS:
            continue
        if examined >= max(0, min(limit, 3)):
            break
        examined += 1
        try:
            response = fetcher(link, timeout=(5, 8))
            response.raise_for_status()
            if urlsplit(response.url).hostname != urlsplit(link).hostname:
                continue
            soup = BeautifulSoup(response.content, 'html.parser')
            tag = soup.select_one('meta[property="og:image"]')
            url = urljoin(link, tag.get('content', '')) if tag else ''
            if url and urlsplit(url).scheme == 'https':
                results.append({
                    'article_id': article.get('id'), 'article_url': link,
                    'title': article.get('title_si'), 'image_url': url,
                    'status': 'event_and_rights_verification_required',
                    'may_download_or_publish': False,
                    'note': 'Publisher preview image only; identity, exact event and reuse permission unverified.'})
        except (requests.RequestException, ValueError) as exc:
            results.append({'article_id': article.get('id'), 'article_url': link,
                            'status': 'discovery_unavailable', 'error': type(exc).__name__})
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    return {'examined': examined, 'candidates': len(results), 'report_file': str(output)}
