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
    commons = {'status': 'not_requested'}
    if inspect_photos:
        try:
            commons = discover_commons_media(articles, limit=limit)
        except Exception as exc:
            commons = {'status': 'unavailable', 'error': type(exc).__name__}
    pexels = {'status': 'not_requested'}
    if inspect_photos:
        try:
            pexels = discover_pexels_media(articles, limit=limit)
        except Exception as exc:
            pexels = {'status': 'unavailable', 'error': type(exc).__name__}
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    return {'examined': examined, 'candidates': len(results),
            'rss_direct_candidates': sum(x.get('source') == 'rss_video_enclosure'
                                         for x in results),
            'rights_approved': 0, 'commons': commons, 'pexels': pexels, 'photos': photos, 'report_file': str(output)}


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


def discover_commons_media(articles, limit=3, output_path='output/commons_candidates.json', fetcher=None):
    """Search reusable Commons media; event identity still requires review."""
    import requests
    from real_photo import permitted, plain
    from urllib.parse import urlsplit
    fetcher = fetcher or requests.get
    results = []
    for article in articles[:max(0, min(limit, 3))]:
        query = article.get('media_search_query') or article.get('title_si', '')
        if not query:
            continue
        try:
            response = fetcher('https://commons.wikimedia.org/w/api.php',
                params={'action': 'query', 'generator': 'search',
                        'gsrsearch': query, 'gsrnamespace': 6, 'gsrlimit': 4,
                        'prop': 'imageinfo', 'iiprop': 'url|mime|extmetadata',
                        'format': 'json'},
                headers={'User-Agent': 'SLNews247/1.0 (media licence review)'},
                timeout=(5, 8))
            response.raise_for_status()
            for page in response.json().get('query', {}).get('pages', {}).values():
                info = (page.get('imageinfo') or [{}])[0]
                meta = info.get('extmetadata', {})
                url = info.get('url', '')
                if not permitted(info) or urlsplit(url).hostname != 'upload.wikimedia.org':
                    continue
                if not info.get('mime', '').startswith(('image/', 'video/')):
                    continue
                results.append({
                    'article_id': article.get('id'), 'article_url': article.get('link'),
                    'media_url': url, 'source_page': info.get('descriptionurl'),
                    'creator': plain(meta.get('Artist', {}).get('value')),
                    'license': plain(meta.get('LicenseShortName', {}).get('value')),
                    'license_url': plain(meta.get('LicenseUrl', {}).get('value')),
                    'source': 'Wikimedia Commons', 'file_title': page.get('title'),
                    'status': 'licence_candidate_event_review_required',
                    'verified_event': False, 'may_download_or_publish': False})
        except (requests.RequestException, ValueError, TypeError) as exc:
            results.append({'article_id': article.get('id'), 'status': 'source_unavailable',
                            'error': type(exc).__name__})
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    return {'candidates': len(results), 'report_file': str(output)}


def discover_pexels_media(articles, limit=3, output_path='output/pexels_candidates.json', fetcher=None):
    """Pexels photo/video review leads; never presume stock depicts an event."""
    import os
    import requests
    key = os.getenv('PEXELS_API_KEY', '').strip()
    if not key:
        return {'status': 'missing_api_key', 'candidates': 0}
    fetcher = fetcher or requests.get
    results = []
    for article in articles[:max(0, min(limit, 3))]:
        query = article.get('media_search_query') or article.get('title_si', '')
        if not query:
            continue
        for kind, endpoint, field in (
                ('photo', 'https://api.pexels.com/v1/search', 'photos'),
                ('video', 'https://api.pexels.com/v1/videos/search', 'videos')):
            try:
                response = fetcher(endpoint, headers={'Authorization': key},
                                   params={'query': query, 'per_page': 3}, timeout=(5, 8))
                if response.status_code == 429:
                    break
                response.raise_for_status()
                for item in response.json().get(field, []):
                    results.append({
                        'article_id': article.get('id'), 'article_url': article.get('link'),
                        'source': 'Pexels', 'kind': kind, 'source_page': item.get('url'),
                        'creator': item.get('photographer') or (item.get('user') or {}).get('name'),
                        'media_url': (item.get('src') or {}).get('original') if kind == 'photo' else None,
                        'video_files': item.get('video_files', []) if kind == 'video' else [],
                        'license_url': 'https://www.pexels.com/license/',
                        'provider_credit_url': 'https://www.pexels.com',
                        'status': 'stock_media_event_and_terms_review_required',
                        'verified_event': False, 'may_download_or_publish': False})
            except (requests.RequestException, ValueError, TypeError) as exc:
                results.append({'article_id': article.get('id'), 'kind': kind,
                                'status': 'source_unavailable', 'error': type(exc).__name__})
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    return {'status': 'checked', 'candidates': len(results), 'report_file': str(output)}
