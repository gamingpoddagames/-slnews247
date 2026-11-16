"""Reviewed original Sinhala briefs and exact-story official video references."""
import json
from pathlib import Path
from urllib.parse import urlsplit, parse_qs

BRIEFS = Path('data/editorial_briefs.json')


def brief_for(article):
    if not BRIEFS.exists():
        return {}
    brief = json.loads(BRIEFS.read_text()).get(article['id'], {})
    if (brief.get('article_url') != article.get('link') or brief.get('facts_reviewed') is not True
            or not brief.get('source_refs') or not brief.get('body_si')):
        return {}
    return brief


def official_video_for(article):
    brief = brief_for(article)
    url = brief.get('official_video_url', '')
    if brief.get('official_video_verified') is not True or not brief.get('official_video_evidence'):
        return None
    parsed = urlsplit(url)
    if parsed.scheme != 'https':
        return None
    host = parsed.hostname or ''
    if host in ('www.youtube.com', 'youtube.com'):
        if parsed.path != '/watch' or not parse_qs(parsed.query).get('v'):
            return None
    elif host == 'youtu.be':
        if not parsed.path.strip('/'):
            return None
    else:
        return None
    return url
