"""Collect RSS-supplied direct video attachments, without assuming reuse rights.

Only https MP4/WebM files are considered; arbitrary embedded players and
YouTube pages are links, not media bytes. All candidates require editorial
and rights verification before they may be downloaded for publishing.
"""
from urllib.parse import urlsplit

EXTENSIONS = ('.mp4', '.webm', '.mov', '.m4v')
MIME_TYPES = {'video/mp4', 'video/webm', 'video/quicktime', 'video/x-m4v'}


def is_direct_video(url, mime=''):
    if not isinstance(url, str):
        return False
    parts = urlsplit(url)
    if parts.scheme != 'https' or not parts.hostname or parts.username or parts.password:
        return False
    if parts.hostname.lower() in ('youtube.com', 'www.youtube.com', 'youtu.be',
                                  'youtube-nocookie.com', 'www.youtube-nocookie.com'):
        return False
    media_type = str(mime or '').split(';', 1)[0].strip().lower()
    return parts.path.lower().endswith(EXTENSIONS) or (
        media_type in MIME_TYPES and not parts.path.lower().endswith(('.html','.htm','.php','.xml'))
    )


def rss_video_urls(item):
    """Read RSS enclosures, media:content and Atom links from feedparser."""
    candidates = []
    for enclosure in item.get('enclosures', []):
        if enclosure.get('href'):
            candidates.append((enclosure['href'], enclosure.get('type','')))
    for media in item.get('media_content', []):
        if media.get('url'):
            candidates.append((media['url'], media.get('type','')))
    for link in item.get('links', []):
        if link.get('rel') in ('enclosure', 'alternate') and link.get('href'):
            candidates.append((link['href'],link.get('type','')))
    unique = []
    for url, mime in candidates:
        if is_direct_video(url,mime) and url not in unique:
            unique.append(url)
    return unique[:5]
