"""Discover exact-article publisher video players for rights review; never download them."""
import json
import re
from pathlib import Path

def discover_candidates(articles, limit=3, output_path='output/footage_candidates.json', finder=None):
    if finder is None:
        from publisher_videos import discover_video
        finder = discover_video
    results = []
    examined = 0
    for article in articles:
        if examined >= limit:
            break
        if not re.search(r'video|වීඩියෝ', article.get('title_si', ''), re.I):
            continue
        examined += 1
        try:
            found = finder(article)
        except Exception as exc:
            results.append({'article_id': article.get('id'), 'article_url': article.get('link'),
                            'status': 'discovery_unavailable', 'error': type(exc).__name__})
            continue
        if found:
            results.append({'article_id': article.get('id'), 'title': article.get('title_si'),
                            'article_url': article.get('link'), 'player_url': found,
                            'status': 'rights_verification_required',
                            'may_download_or_publish': False})
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    return {'examined': examined, 'candidates': len(results),
            'rights_approved': 0, 'report_file': str(output)}
