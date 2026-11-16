"""Share an exact article's publisher-embedded player; never copy its footage."""
import json
import re
import time
from pathlib import Path
from urllib.parse import urlsplit, parse_qs, urljoin
import requests
from bs4 import BeautifulSoup

CACHE = Path('data/publisher_video_links.json')
HOSTS = {'siyathanews.lk','www.siyathanews.lk','www.itnnews.lk','itnnews.lk',
         'www.hirunews.lk','hirunews.lk','sinhala.adaderana.lk','sinhala.newsfirst.lk',
         'www.lankadeepa.lk','lankadeepa.lk','tv.rupavahini.lk','www.swarnavahini.lk'}


def youtube_watch(url):
    parsed=urlsplit(urljoin('https://www.youtube.com/',url))
    if parsed.scheme!='https':
        return None
    host=parsed.hostname or ''
    video_id=None
    if host in ('www.youtube.com','youtube.com','www.youtube-nocookie.com','youtube-nocookie.com'):
        if parsed.path.startswith('/embed/'):
            video_id=parsed.path.split('/')[2]
        elif parsed.path=='/watch':
            video_id=parse_qs(parsed.query).get('v',[''])[0]
    elif host=='youtu.be':
        video_id=parsed.path.strip('/')
    if video_id not in ('live_stream', 'videoseries') and video_id and re.fullmatch('[A-Za-z0-9_-]{11}',video_id):
        return 'https://www.youtube.com/watch?v='+video_id
    return None


def extract_video(html):
    soup=BeautifulSoup(html,'html.parser')
    # Exact editorial content only: never sidebar, footer or global channel livestream.
    body=soup.select_one('.td-post-content, .entry-content, .article-content, .post-content, [itemprop="articleBody"]')
    if body is None:
        return None
    links=set()
    for element in body.select('iframe[src], iframe[data-src], a[href]'):
        url=element.get('src') or element.get('data-src') or element.get('href')
        watch=youtube_watch(url or '')
        if watch:
            links.add(watch)
    return next(iter(links)) if len(links)==1 else None


def discover_video(article):
    link=article.get('link','')
    if urlsplit(link).hostname not in HOSTS or urlsplit(link).scheme!='https':
        return None
    # Only video-labelled articles are fetched to keep the fast scan bounded.
    if not re.search(r'video|වීඩියෝ',article.get('title_si',''),re.I):
        return None
    cache=json.loads(CACHE.read_text()) if CACHE.exists() else {}
    old=cache.get(article['id'],{})
    if old.get('article_url')==link and time.time()-old.get('checked_at',0)<3600:
        return old.get('url')
    found=None
    try:
        response=requests.get(link,timeout=(5,12))
        response.raise_for_status()
        if urlsplit(response.url).hostname not in HOSTS:
            return None
        found=extract_video(response.content)
    except (requests.RequestException,ValueError):
        pass
    cache[article['id']]={'article_url':link,'url':found,'checked_at':time.time(),
                           'evidence':'Single YouTube player inside publisher article content; link sharing only'}
    CACHE.parent.mkdir(parents=True,exist_ok=True)
    CACHE.write_text(json.dumps(dict(list(cache.items())[-500:]),ensure_ascii=False,indent=2),encoding='utf-8')
    return found
