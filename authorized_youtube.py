"""Download a publisher YouTube video ONLY with a recorded exact-video reuse grant.

A public RSS/YouTube URL is NOT permission. No scraping of private, DRM-
protected, paywalled or login-restricted content. Preserve required marks.
"""
import hashlib
import json
import subprocess
from pathlib import Path

from publisher_videos import youtube_watch

MAX_BYTES = 60_000_000


def approved_youtube_asset(article, asset):
    if not isinstance(asset, dict):
        return False
    url = youtube_watch(asset.get('youtube_url', ''))
    if not url:
        return False
    matched = url in article.get('rss_video_urls', []) or url == article.get('official_video_url')
    # Editorial grants can attach a manually verified embedded URL, in which case
    # verified_article_video_url must be populated by the rights reviewer.
    matched = matched or url == asset.get('verified_article_video_url')
    return bool(matched
                and asset.get('article_url') == article.get('link')
                and asset.get('verified_event') is True
                and asset.get('real_footage_verified') is True
                and asset.get('rights_verified') is True
                and asset.get('audio_replacement_permitted') is True
                and asset.get('republishing_permitted') is True
                and (asset.get('attribution_required') is False
                     or (asset.get('attribution_required') is True
                         and all(asset.get(k) for k in ('creator','license','license_url','source_page'))))
                and asset.get('rights_evidence')
                and asset.get('verification_notes'))


def download_approved_youtube(article, asset, directory='assets/events'):
    if not approved_youtube_asset(article, asset):
        return None
    url = youtube_watch(asset['youtube_url'])
    folder = Path(directory)
    folder.mkdir(parents=True, exist_ok=True)
    destination = folder / (article['id'] + '.mp4')
    if destination.is_file():
        from video import probe_footage
        probe_footage(str(destination))
        return str(destination)
    temp = folder / (article['id'] + '.download.mp4')
    try:
        # yt-dlp only receives a specific approved watch URL; do not extract
        # playlists, cookies, authentication tokens or unrelated videos.
        command = [
            'yt-dlp', '--no-playlist', '--no-progress', '--no-warnings',
            '--no-overwrites',
            '--max-filesize', '60M', '--socket-timeout', '15',
            '--retries', '2', '--merge-output-format', 'mp4',
            '-f', 'b[ext=mp4][height<=720]/bv[ext=mp4][height<=720]+ba[ext=m4a]/b[height<=720]',
            '-o', str(temp), url
        ]
        subprocess.run(command, check=True, timeout=150, capture_output=True, text=True)
        if not temp.is_file() or temp.stat().st_size > MAX_BYTES:
            raise ValueError('Missing or oversized licensed YouTube download')
        from video import probe_footage
        probe_footage(str(temp))
        digest = hashlib.sha256(temp.read_bytes()).hexdigest()
        if asset.get('sha256') and digest != asset['sha256']:
            raise ValueError('Approved video hash mismatch')
        temp.replace(destination)
        return str(destination)
    finally:
        temp.unlink(missing_ok=True)
