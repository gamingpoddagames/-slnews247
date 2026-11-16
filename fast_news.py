"""Fast Sri Lankan Sinhala RSS alerts with durable per-destination receipts."""
import hashlib
import json
import os
import re
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import feedparser
import requests
from bs4 import BeautifulSoup

SOURCES = [
    ('Ada Derana Sinhala', 'https://sinhala.adaderana.lk/rss.php'),
    ('Dinamina', 'https://www.dinamina.lk/feed/'),
    ('Divaina', 'https://divaina.lk/feed/'),
    ('Lankadeepa Latest', 'https://www.lankadeepa.lk/rss/latest_news/1'),
    ('Lankadeepa Business', 'https://www.lankadeepa.lk/rss/business/9'),
]
STATE_FILE = Path('data/sri_lanka_delivery.json')
MAX_AGE = 12 * 3600


def clean(text):
    text = BeautifulSoup(str(text or ''), 'html.parser').get_text(' ')
    return re.sub(r'\s+', ' ', text.replace('\xad', '')).strip()


def shorten(text, size):
    text = clean(text)
    return text if len(text) <= size else text[:size].rsplit(' ', 1)[0] + '…'


def fingerprint(title):
    normalized = ''.join(c for c in unicodedata.normalize('NFC', title).lower()
                         if unicodedata.category(c)[0] in 'LMN')
    return hashlib.sha256(normalized.encode()).hexdigest()[:24]


def parse_feed(content, source, now):
    feed = feedparser.parse(content)
    articles = []
    for item in feed.entries[:40]:
        title, link = clean(item.get('title')), item.get('link', '')
        if not re.search('[\u0d80-\u0dff]', title) or not link.startswith('https://'):
            continue
        parsed = item.get('published_parsed') or item.get('updated_parsed')
        if parsed:
            import calendar
            published = calendar.timegm(parsed)
        else:
            try:
                published = datetime.fromisoformat(item.get('published', '').replace('Z', '+00:00')).timestamp()
            except (ValueError, TypeError):
                continue
        if not 0 <= now - published <= MAX_AGE:
            continue
        # A short excerpt with attribution, never the full article or publisher photo.
        summary = shorten(item.get('summary', ''), 200)
        if fingerprint(summary) == fingerprint(title):
            summary = ''
        articles.append({'id': fingerprint(title), 'title_si': shorten(title, 220),
                         'summary_si': summary, 'link': link, 'source': source,
                         'published': published})
    return articles, len(feed.entries)


def collect(now):
    def fetch(pair):
        source, url = pair
        try:
            response = requests.get(url, timeout=(5, 15))
            response.raise_for_status()
            articles, total = parse_feed(response.content, source, now)
            return articles, {'source': source, 'http': response.status_code,
                              'entries': total, 'fresh_sinhala': len(articles)}
        except Exception as exc:
            return [], {'source': source, 'error': type(exc).__name__}
    articles, health = [], []
    with ThreadPoolExecutor(max_workers=5) as pool:
        for items, status in pool.map(fetch, SOURCES):
            articles.extend(items)
            health.append(status)
    unique = {}
    for article in sorted(articles, key=lambda a: a['published'], reverse=True):
        unique.setdefault(article['id'], article)
    return list(unique.values()), health


def save(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    temp = STATE_FILE.with_suffix('.tmp')
    temp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(STATE_FILE)


def caption(article):
    from zoneinfo import ZoneInfo
    stamp = datetime.fromtimestamp(article['published'], ZoneInfo('Asia/Colombo')).strftime('%Y-%m-%d %H:%M')
    return (f"🇱🇰 {article['title_si']}\n\n" +
            (f"{article['summary_si']}\n\n" if article['summary_si'] else '') +
            f"{stamp} | ශ්‍රී ලංකා වේලාව\nSL News 247")


def send_text(platform, article):
    from media import post_image
    try:
        image_path = post_image(article)
    except Exception as exc:
        # No unlicensed substitute and no uncertain platform request on media failure.
        return {'error': 'photo_preparation_failed', 'type': type(exc).__name__}
    if platform == 'telegram':
        token, chat = os.getenv('TG_TOKEN'), os.getenv('TG_CHAT_ID')
        if not token or not chat:
            return {'error': 'missing_credentials'}
        with open(image_path, 'rb') as photo:
            response = requests.post(f'https://api.telegram.org/bot{token}/sendPhoto',
                                     data={'chat_id': chat, 'caption': caption(article)[:1024]},
                                     files={'photo': photo}, timeout=(5, 45))
        data = response.json()
        if response.ok and data.get('ok'):
            return {'id': str(data['result']['message_id']), 'format': 'photo'}
    else:
        page, token = os.getenv('FB_PAGE_ID'), os.getenv('FB_PAGE_TOKEN')
        if not page or not token:
            return {'error': 'missing_credentials'}
        with open(image_path, 'rb') as photo:
            response = requests.post(f'https://graph.facebook.com/v22.0/{page}/photos',
                                     data={'access_token': token, 'caption': caption(article)},
                                     files={'source': photo}, timeout=(5, 60))
        data = response.json()
        if response.ok and data.get('id'):
            return {'id': str(data.get('post_id') or data['id']), 'format': 'photo'}
    return {'error': 'api_rejected', 'http': response.status_code,
            'code': data.get('error', {}).get('code')}


def deliver(state, articles, now, preview=False, sender=send_text):
    results = {name: {'sent': 0, 'failed': 0, 'uncertain': 0} for name in ('telegram', 'facebook')}
    records = state.setdefault('stories', {})
    limit = max(1, min(20, int(os.getenv('MAX_NEWS_PER_RUN', '5'))))
    selected = []
    for article in articles:
        record = records.setdefault(article['id'], {'article': article, 'receipts': {}})
        if all(name in record['receipts'] or record.get('uncertain', {}).get(name) for name in results):
            continue
        selected.append(article)
        if len(selected) >= limit:
            break
    for article in selected:
        record = records[article['id']]
        for name in results:
            if name in record['receipts']:
                continue
            if preview:
                continue
            # Persist intent before request. Lost responses require inspection, not blind retry.
            if record.setdefault('uncertain', {}).get(name):
                results[name]['uncertain'] += 1
                continue
            record['uncertain'][name] = True
            save(state)
            try:
                result = sender(name, article)
            except Exception as exc:
                results[name]['uncertain'] += 1
                print(name, 'unconfirmed request:', type(exc).__name__)
                continue
            if result.get('id'):
                record['receipts'][name] = {'id': result['id'], 'at': now, 'format': result.get('format', 'text')}
                record['uncertain'].pop(name, None)
                results[name]['sent'] += 1
            else:
                record['uncertain'].pop(name, None)
                results[name]['failed'] += 1
                record.setdefault('errors', {})[name] = result
            save(state)
    return results, selected


def maybe_video(state, articles, now, preview):
    if not articles:
        return 'no_fresh_story'
    if not preview and now - state.get('last_video_at', 0) < 1800 and state.get('video_style') == 'photo-v1':
        return 'waiting_for_30_minute_interval'
    recent = state.setdefault('videos', {})
    candidate = next((a for a in articles if a['id'] not in recent), None)
    if not candidate:
        return 'no_new_video_story'
    from voice import create_voice
    from video import create_video
    video = 'output/news.mp4'
    Path('assets').mkdir(exist_ok=True)
    script = candidate['title_si'] + '. ' + candidate['summary_si']
    if not create_voice(script, 'assets/voice.mp3'):
        return 'voice_failed'
    from media import choose_photo
    photo = choose_photo(candidate)
    create_video(photo, 'assets/voice.mp3', candidate['title_si'], candidate['summary_si'], video)
    if preview:
        return 'preview_created'
    # Prevent duplicate automatic uploads after an ambiguous video request.
    recent[candidate['id']] = {'status': 'started', 'at': now, 'destinations': {}}
    state['video_style'] = 'photo-v1'
    state['last_video_at'] = now
    save(state)
    from telegram import upload_news as telegram
    from facebook import upload_news as facebook
    from tiktok import upload_news as tiktok
    publishers = [('telegram', telegram), ('facebook', facebook)]
    if os.getenv('TIKTOK_ENABLED', 'false').lower() == 'true':
        publishers.append(('tiktok', tiktok))
    for name, publish in publishers:
        try:
            ok = publish(video, candidate)
        except Exception:
            ok = False
        recent[candidate['id']]['destinations'][name] = 'accepted' if ok else 'unconfirmed_or_failed'
        save(state)
    recent[candidate['id']]['status'] = 'attempted'
    save(state)
    return recent[candidate['id']]


def main():
    now = time.time()
    preview = os.getenv('PREVIEW_ONLY', 'false').lower() == 'true'
    Path('output').mkdir(exist_ok=True)
    state = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}
    articles, health = collect(now)
    # Retain receipts for two days; only publish fresh feed entries.
    state['stories'] = {key: val for key, val in state.get('stories', {}).items()
                        if now - val['article']['published'] < 48 * 3600}
    state['videos'] = {key: val for key, val in state.get('videos', {}).items()
                       if now - val['at'] < 48 * 3600}
    report = {'preview': preview, 'feeds': health, 'fresh_unique_articles': len(articles),
              'tiktok': 'enabled' if os.getenv('TIKTOK_ENABLED', 'false').lower() == 'true' else 'blocked_authorization_required'}
    delivery, selected = deliver(state, articles, now, preview)
    report['delivery'] = delivery
    Path('output/stories.json').write_text(json.dumps(selected, ensure_ascii=False, indent=2), encoding='utf-8')
    try:
        report['video'] = maybe_video(state, articles, now, preview)
    except Exception as exc:
        report['video'] = 'failed: ' + type(exc).__name__
    report['unconfirmed_headline_requests'] = sum(len(r.get('uncertain', {})) for r in state.get('stories', {}).values())
    report['selected_titles'] = [a['title_si'] for a in selected]
    if not preview:
        state['last_scan_at'] = now
        save(state)
    Path('output/delivery_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))
    if os.getenv('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as handle:
            handle.write('## Sri Lanka news results\n```json\n' + json.dumps(report, ensure_ascii=False, indent=2) + '\n```\n')
    if not any(h.get('entries', 0) for h in health):
        raise RuntimeError('All RSS sources unavailable')
    if report['unconfirmed_headline_requests'] or any(v['failed'] or v['uncertain'] for v in delivery.values()):
        raise RuntimeError('One or more headline destinations failed or need inspection')


if __name__ == '__main__':
    main()
