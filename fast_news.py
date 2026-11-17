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
    ('Siyatha News', 'https://siyathanews.lk/feed/'),
    ('ITN News', 'https://www.itnnews.lk/feed/'),
    ('Lankasara Sinhala', 'https://lankasara.com/si/feed/'),
    ('Newsfirst Sinhala', 'https://sinhala.newsfirst.lk/feed/'),
]
STATE_FILE = Path('data/sri_lanka_delivery.json')
MAX_AGE = 12 * 3600


def clean(text):
    text = BeautifulSoup(str(text or ''), 'html.parser').get_text(' ')
    return re.sub(r'\s+', ' ', text.replace('\xad', '')).strip()


def shorten(text, size):
    text = clean(text)
    return text if len(text) <= size else text[:size].rsplit(' ', 1)[0] + '…'


def complete_sentences(text, limit=1800):
    """Preserve complete reported sentences; discard cut-off RSS fragments."""
    text = clean(text)
    text = re.split(r'The post\b|මේ පිළිබඳ තවත් තොරතුරු පහතින්', text, maxsplit=1)[0].strip()
    text = re.sub(r'https?://\S+', '', text).strip()
    text = re.sub(r'(?:\.{3}|…)+\s*$', '', text).strip()
    sentences = []
    for match in re.finditer(r'[^.!?।\n]+[.!?।]+', text):
        sentence = match.group().strip()
        if len(' '.join(sentences + [sentence])) > limit:
            break
        sentences.append(sentence)
    return ' '.join(sentences)


def relevant_summary(title, body):
    """Reject unrelated feed descriptions, not just text truncation."""
    if not body or len(body) < 45:
        return False
    # Match meaningful Sinhala/Latin words; do not translate English names.
    words = lambda value: {
        w.casefold() for w in re.findall(r'[\u0D80-\u0DFF\w]+', value)
        if len(w) >= 5
    }
    excluded = {'ප්‍රදේශයේ', 'සම්බන්ධයෙන්', 'අදාල', 'අදාළ', 'පිළිබඳව',
                'පිළිබඳ', 'සඳහා', 'සිදුවූ', 'තිබෙනවා', 'තිබේ',
                'කරයි', 'කෙරේ', 'ලංකාවේ', 'ලංකා', 'පුවතක්'}
    keywords = words(title) - excluded
    if not keywords:
        return False
    return bool(keywords & words(body))


def publishable(article):
    """Fail closed for empty, unfinished, or mismatched news stories."""
    from editorial import brief_for
    reviewed = brief_for(article) if article.get('id') and article.get('link') else {}
    raw = reviewed.get('body_si', '') if reviewed else article.get('summary_si', '')
    text = complete_sentences(raw, 3500)
    return bool(text and (reviewed or relevant_summary(article['title_si'], text)))


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
        summary = complete_sentences(item.get('summary', ''), 1800)
        if fingerprint(summary) == fingerprint(title) or not relevant_summary(title, summary):
            summary = ''
        articles.append({'id': fingerprint(title), 'title_si': title,
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
                              'entries': total, 'fresh_sinhala': len(articles), 'feed_url': url}
        except Exception as exc:
            return [], {'source': source, 'error': type(exc).__name__, 'http': getattr(getattr(exc, 'response', None), 'status_code', None)}
    articles, health = [], []
    with ThreadPoolExecutor(max_workers=8) as pool:
        for items, status in pool.map(fetch, SOURCES):
            articles.extend(items)
            health.append(status)
    # One-off, fact-checked urgent newsroom items (original summaries only).
    # Honor the same 12-hour freshness filter and existing delivery receipts.
    urgent_path = Path('data/urgent_news.json')
    if urgent_path.exists():
        try:
            for urgent in json.loads(urgent_path.read_text(encoding='utf-8')).get('stories', []):
                if (isinstance(urgent, dict) and urgent.get('id')
                        and urgent.get('title_si') and urgent.get('link', '').startswith('https://')
                        and isinstance(urgent.get('published'), (int, float))
                        and 0 <= now - urgent['published'] <= MAX_AGE):
                    articles.append(urgent)
        except (ValueError, OSError, TypeError, KeyError) as exc:
            print('Urgent newsroom source invalid:', type(exc).__name__)
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
    title = re.sub(r'\s*\((?:VIDEO|වීඩියෝ)\)', '', article['title_si'], flags=re.I)
    title = title.removeprefix('විස්තරාත්මක පුවත | ')
    from editorial import brief_for
    reviewed = brief_for(article) if article.get('id') and article.get('link') else {}
    body = reviewed.get('body_si', '') if reviewed else article.get('summary_si', '')
    body = complete_sentences(body, 3500)
    return f"🇱🇰 {title}\n\n{body}\n\n🕒 {stamp}\n━━━━━━━━━━━━\nSL News 247"


def send_text(platform, article):
    if not article.get('sample') and not publishable(article):
        return {'error': 'missing_or_unrelated_story_details'}
    from image import news_card
    from media import post_image
    try:
        # Original branded card for every headline; licensed event photos remain optional.
        # This card is graphic design, not a claimed photograph of the event.
        image_path = post_image(article) or news_card(article)
        if platform == 'telegram' and len(caption(article)) > 1024:
            image_path = None
    except Exception as exc:
        # No unlicensed substitute and no uncertain platform request on media failure.
        image_path = None
        print('No verified event photo:', type(exc).__name__)
    message = caption(article)
    if platform == 'telegram' and len(message) > 4096:
        return {'error': 'caption_too_long_review_required'}
    if platform == 'telegram':
        token, chat = os.getenv('TG_TOKEN'), os.getenv('TG_CHAT_ID')
        if not token or not chat:
            return {'error': 'missing_credentials'}
        if image_path:
            with open(image_path, 'rb') as photo:
                response = requests.post(f'https://api.telegram.org/bot{token}/sendPhoto',
                                         data={'chat_id': chat, 'caption': message},
                                         files={'photo': photo}, timeout=(5, 45))
        else:
            response = requests.post(f'https://api.telegram.org/bot{token}/sendMessage',
                                     json={'chat_id': chat, 'text': message,
                                           'link_preview_options': {'is_disabled': not bool(article.get('official_video_url'))}}, timeout=(5, 30))
        data = response.json()
        if response.ok and data.get('ok'):
            return {'id': str(data['result']['message_id']), 'format': 'photo' if image_path else 'text'}
    else:
        page, token = os.getenv('FB_PAGE_ID'), os.getenv('FB_PAGE_TOKEN')
        if not page or not token:
            return {'error': 'missing_credentials'}
        if image_path:
            with open(image_path, 'rb') as photo:
                response = requests.post(f'https://graph.facebook.com/v22.0/{page}/photos',
                                         data={'access_token': token, 'caption': caption(article)},
                                         files={'source': photo}, timeout=(5, 60))
        else:
            response = requests.post(f'https://graph.facebook.com/v22.0/{page}/feed',
                                     data={'access_token': token, 'message': caption(article)}, timeout=(5, 45))
        data = response.json()
        if response.ok and data.get('id'):
            return {'id': str(data.get('post_id') or data['id']), 'format': 'photo' if image_path else 'text'}
    return {'error': 'api_rejected', 'http': response.status_code,
            'code': data.get('error', {}).get('code')}


def deliver(state, articles, now, preview=False, sender=send_text):
    results = {name: {'sent': 0, 'failed': 0, 'uncertain': 0} for name in ('telegram', 'facebook')}
    records = state.setdefault('stories', {})
    limit = max(1, min(20, int(os.getenv('MAX_NEWS_PER_RUN', '10'))))
    selected = []
    for article in articles:
        if not publishable(article):
            continue
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
    if not preview and now - state.get('last_video_at', 0) < 900 and state.get('video_style') == 'real-footage-v1':
        return 'waiting_for_15_minute_interval'
    recent = state.setdefault('videos', {})
    candidate = next((a for a in articles if a['id'] not in recent), None)
    if not candidate:
        return share_official_video(state, articles, now, preview)
    from media import choose_video
    from editorial import brief_for
    candidate = None
    footage = None
    for article in articles:
        if article['id'] in recent:
            continue
        if not brief_for(article):
            continue
        footage = choose_video(article)
        if footage:
            candidate = article
            break
    if not candidate:
        return share_official_video(state, articles, now, preview)
    from video import create_footage_video
    video = 'output/news.mp4'
    from voice import create_voice
    brief = brief_for(candidate)
    audio = 'output/news_narration.mp3'
    Path(audio).unlink(missing_ok=True)
    if not create_voice(brief['body_si'], audio):
        return 'skipped_narration_failed'
    create_footage_video(footage, candidate['title_si'], candidate['summary_si'], video, audio_path=audio)
    if preview:
        return 'preview_created'
    # Prevent duplicate automatic uploads after an ambiguous video request.
    recent[candidate['id']] = {'status': 'started', 'at': now, 'destinations': {}}
    state['video_style'] = 'real-footage-v1'
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


def share_official_video(state, articles, now, preview):
    return 'skipped_no_verified_event_video_or_official_link'

    from editorial import official_video_for
    history = state.setdefault('official_video_links', {})
    checks = 0
    for article in articles:
        existing = history.get(article['id'], {}).get('destinations', {})
        if all(name in existing for name in ('telegram', 'facebook')):
            continue
        url = official_video_for(article)
        if not url and checks < 3 and re.search(r'video|වීඩියෝ', article['title_si'], re.I):
            from publisher_videos import discover_video
            checks += 1
            url = discover_video(article)
        if not url:
            continue
        record = history.setdefault(article['id'], {'url': url, 'destinations': {}})
        if all(name in record['destinations'] for name in ('telegram', 'facebook')):
            continue
        if preview:
            return {'format': 'official_video_link', 'url': url, 'preview': True}
        linked = dict(article, official_video_url=url)
        for name in ('telegram', 'facebook'):
            if name in record['destinations']:
                continue
            # Persist intent: a lost response must not trigger blind duplicate sharing.
            record['destinations'][name] = {'status': 'unconfirmed'}
            save(state)
            try:
                result = send_text(name, linked)
            except Exception:
                result = {'error': 'unconfirmed_request'}
            record['destinations'][name] = result
            save(state)
        return {'format': 'official_video_link', 'url': url, 'destinations': record['destinations']}
    return 'skipped_no_verified_event_video_or_official_link'


def share_editorial_update(state, articles, now, preview):
    from editorial import brief_for
    history = state.setdefault('editorial_updates', {})
    for article in articles:
        brief = brief_for(article)
        if not brief or article['id'] in history:
            continue
        if preview:
            return 'preview_only'
        report = history.setdefault(article['id'], {})
        detailed = dict(article, title_si='විස්තරාත්මක පුවත | ' + article['title_si'], summary_si=brief['body_si'])
        for name in ('telegram', 'facebook'):
            report[name] = {'status': 'unconfirmed'}
            save(state)
            try:
                report[name] = send_text(name, detailed)
            except Exception:
                report[name] = {'error': 'unconfirmed_request'}
            save(state)
        return report
    return 'no_new_reviewed_brief'


def main():
    now = time.time()
    preview = os.getenv('PREVIEW_ONLY', 'false').lower() == 'true'
    Path('output').mkdir(exist_ok=True)
    state = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}

    # Owner-authorized one-time Facebook design sample, checkpointed before sending.
    if not preview and 'facebook_design_sample_v1' not in state:
        state['facebook_design_sample_v1'] = {'status': 'unconfirmed'}
        save(state)
        sample = {'id': 'design_sample_v1', 'sample': True, 'published': now,
                  'title_si': 'පුවතේ වැදගත්ම තොරතුරු එකම තැනක',
                  'summary_si': 'ආදර්ශ පළ කිරීමකි.\n\nමෙය SL News 247 නව පුවත් සැලසුම පෙන්වීම සඳහා පළ කරන ආදර්ශයකි. රතු පසුබිම මත සුදු පැහැයෙන් සිරස්තලයත්, කහ පැහැයෙන් වැදගත් කොටසත් දක්වා තිබෙනවා.\n\nඉදිරි පුවත් සඳහා තහවුරු කළ කරුණු පැහැදිලි ඡේද ලෙස මෙහි ඇතුළත් කෙරෙනවා. මෙය සැබෑ සිද්ධියක් පිළිබඳ පුවතක් නොවේ.'}
        state['facebook_design_sample_v1'] = send_text('facebook', sample)
        save(state)

    articles, health = collect(now)
    # Retain receipts for two days; only publish fresh feed entries.
    state['stories'] = {key: val for key, val in state.get('stories', {}).items()
                        if now - val['article']['published'] < 48 * 3600}
    state['videos'] = {key: val for key, val in state.get('videos', {}).items()
                       if now - val['at'] < 48 * 3600}
    report = {'preview': preview, 'feeds': health, 'fresh_unique_articles': len(articles),
              'tiktok': 'enabled' if os.getenv('TIKTOK_ENABLED', 'false').lower() == 'true' else 'blocked_authorization_required'}
    delivery, selected = deliver(state, articles, now, preview)
    report['quality_gate_skipped'] = sum(not publishable(article) for article in articles)
    report['delivery'] = delivery
    report['editorial_update'] = share_editorial_update(state, articles, now, preview)
    Path('output/stories.json').write_text(json.dumps(selected, ensure_ascii=False, indent=2), encoding='utf-8')
    try:
        report['video'] = maybe_video(state, articles, now, preview)
    except Exception as exc:
        report['video'] = 'failed: ' + type(exc).__name__
    report['unconfirmed_headline_requests'] = sum(len(r.get('uncertain', {})) for r in state.get('stories', {}).values())
    report['selected_titles'] = [a['title_si'] for a in selected]
    if not preview:
        Path('data/source_health.json').write_text(json.dumps({'checked_at': now, 'configured_feeds': len(SOURCES), 'sources': health}, ensure_ascii=False, indent=2), encoding='utf-8')
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
, '', text).strip()
    if not text:
        return ''
    sentences = []
    for match in re.finditer(r'[^.!?।\\n]+[.!?।]+', text):
        sentence = match.group().strip()
        if len(' '.join(sentences + [sentence])) > limit:
            break
        sentences.append(sentence)
    return ' '.join(sentences)


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
                              'entries': total, 'fresh_sinhala': len(articles), 'feed_url': url}
        except Exception as exc:
            return [], {'source': source, 'error': type(exc).__name__, 'http': getattr(getattr(exc, 'response', None), 'status_code', None)}
    articles, health = [], []
    with ThreadPoolExecutor(max_workers=8) as pool:
        for items, status in pool.map(fetch, SOURCES):
            articles.extend(items)
            health.append(status)
    # One-off, fact-checked urgent newsroom items (original summaries only).
    # Honor the same 12-hour freshness filter and existing delivery receipts.
    urgent_path = Path('data/urgent_news.json')
    if urgent_path.exists():
        try:
            for urgent in json.loads(urgent_path.read_text(encoding='utf-8')).get('stories', []):
                if (isinstance(urgent, dict) and urgent.get('id')
                        and urgent.get('title_si') and urgent.get('link', '').startswith('https://')
                        and isinstance(urgent.get('published'), (int, float))
                        and 0 <= now - urgent['published'] <= MAX_AGE):
                    articles.append(urgent)
        except (ValueError, OSError, TypeError, KeyError) as exc:
            print('Urgent newsroom source invalid:', type(exc).__name__)
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
    title = re.sub(r'\s*\((?:VIDEO|වීඩියෝ)\)', '', article['title_si'], flags=re.I)
    title = title.removeprefix('විස්තරාත්මක පුවත | ')
    body = re.sub(r'https?://\S+', '', article['summary_si'])
    body = re.split(r'The post|මේ පිළිබඳ තවත් තොරතුරු පහතින්', body)[0].strip()
    return f"🇱🇰 {title}\n\n{body}\n\n🕒 {stamp}\n━━━━━━━━━━━━\nSL News 247"


def send_text(platform, article):
    from image import news_card
    from media import post_image
    try:
        # Original branded card for every headline; licensed event photos remain optional.
        # This card is graphic design, not a claimed photograph of the event.
        image_path = post_image(article) or news_card(article)
        if platform == 'telegram' and len(caption(article)) > 1024:
            image_path = None
    except Exception as exc:
        # No unlicensed substitute and no uncertain platform request on media failure.
        image_path = None
        print('No verified event photo:', type(exc).__name__)
    if platform == 'telegram':
        token, chat = os.getenv('TG_TOKEN'), os.getenv('TG_CHAT_ID')
        if not token or not chat:
            return {'error': 'missing_credentials'}
        if image_path:
            with open(image_path, 'rb') as photo:
                response = requests.post(f'https://api.telegram.org/bot{token}/sendPhoto',
                                         data={'chat_id': chat, 'caption': caption(article)[:1024]},
                                         files={'photo': photo}, timeout=(5, 45))
        else:
            response = requests.post(f'https://api.telegram.org/bot{token}/sendMessage',
                                     json={'chat_id': chat, 'text': caption(article)[:4096],
                                           'link_preview_options': {'is_disabled': not bool(article.get('official_video_url'))}}, timeout=(5, 30))
        data = response.json()
        if response.ok and data.get('ok'):
            return {'id': str(data['result']['message_id']), 'format': 'photo' if image_path else 'text'}
    else:
        page, token = os.getenv('FB_PAGE_ID'), os.getenv('FB_PAGE_TOKEN')
        if not page or not token:
            return {'error': 'missing_credentials'}
        if image_path:
            with open(image_path, 'rb') as photo:
                response = requests.post(f'https://graph.facebook.com/v22.0/{page}/photos',
                                         data={'access_token': token, 'caption': caption(article)},
                                         files={'source': photo}, timeout=(5, 60))
        else:
            response = requests.post(f'https://graph.facebook.com/v22.0/{page}/feed',
                                     data={'access_token': token, 'message': caption(article)}, timeout=(5, 45))
        data = response.json()
        if response.ok and data.get('id'):
            return {'id': str(data.get('post_id') or data['id']), 'format': 'photo' if image_path else 'text'}
    return {'error': 'api_rejected', 'http': response.status_code,
            'code': data.get('error', {}).get('code')}


def deliver(state, articles, now, preview=False, sender=send_text):
    results = {name: {'sent': 0, 'failed': 0, 'uncertain': 0} for name in ('telegram', 'facebook')}
    records = state.setdefault('stories', {})
    limit = max(1, min(20, int(os.getenv('MAX_NEWS_PER_RUN', '10'))))
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
    if not preview and now - state.get('last_video_at', 0) < 900 and state.get('video_style') == 'real-footage-v1':
        return 'waiting_for_15_minute_interval'
    recent = state.setdefault('videos', {})
    candidate = next((a for a in articles if a['id'] not in recent), None)
    if not candidate:
        return share_official_video(state, articles, now, preview)
    from media import choose_video
    from editorial import brief_for
    candidate = None
    footage = None
    for article in articles:
        if article['id'] in recent:
            continue
        if not brief_for(article):
            continue
        footage = choose_video(article)
        if footage:
            candidate = article
            break
    if not candidate:
        return share_official_video(state, articles, now, preview)
    from video import create_footage_video
    video = 'output/news.mp4'
    from voice import create_voice
    brief = brief_for(candidate)
    audio = 'output/news_narration.mp3'
    Path(audio).unlink(missing_ok=True)
    if not create_voice(brief['body_si'], audio):
        return 'skipped_narration_failed'
    create_footage_video(footage, candidate['title_si'], candidate['summary_si'], video, audio_path=audio)
    if preview:
        return 'preview_created'
    # Prevent duplicate automatic uploads after an ambiguous video request.
    recent[candidate['id']] = {'status': 'started', 'at': now, 'destinations': {}}
    state['video_style'] = 'real-footage-v1'
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


def share_official_video(state, articles, now, preview):
    return 'skipped_no_verified_event_video_or_official_link'

    from editorial import official_video_for
    history = state.setdefault('official_video_links', {})
    checks = 0
    for article in articles:
        existing = history.get(article['id'], {}).get('destinations', {})
        if all(name in existing for name in ('telegram', 'facebook')):
            continue
        url = official_video_for(article)
        if not url and checks < 3 and re.search(r'video|වීඩියෝ', article['title_si'], re.I):
            from publisher_videos import discover_video
            checks += 1
            url = discover_video(article)
        if not url:
            continue
        record = history.setdefault(article['id'], {'url': url, 'destinations': {}})
        if all(name in record['destinations'] for name in ('telegram', 'facebook')):
            continue
        if preview:
            return {'format': 'official_video_link', 'url': url, 'preview': True}
        linked = dict(article, official_video_url=url)
        for name in ('telegram', 'facebook'):
            if name in record['destinations']:
                continue
            # Persist intent: a lost response must not trigger blind duplicate sharing.
            record['destinations'][name] = {'status': 'unconfirmed'}
            save(state)
            try:
                result = send_text(name, linked)
            except Exception:
                result = {'error': 'unconfirmed_request'}
            record['destinations'][name] = result
            save(state)
        return {'format': 'official_video_link', 'url': url, 'destinations': record['destinations']}
    return 'skipped_no_verified_event_video_or_official_link'


def share_editorial_update(state, articles, now, preview):
    from editorial import brief_for
    history = state.setdefault('editorial_updates', {})
    for article in articles:
        brief = brief_for(article)
        if not brief or article['id'] in history:
            continue
        if preview:
            return 'preview_only'
        report = history.setdefault(article['id'], {})
        detailed = dict(article, title_si='විස්තරාත්මක පුවත | ' + article['title_si'], summary_si=brief['body_si'])
        for name in ('telegram', 'facebook'):
            report[name] = {'status': 'unconfirmed'}
            save(state)
            try:
                report[name] = send_text(name, detailed)
            except Exception:
                report[name] = {'error': 'unconfirmed_request'}
            save(state)
        return report
    return 'no_new_reviewed_brief'


def main():
    now = time.time()
    preview = os.getenv('PREVIEW_ONLY', 'false').lower() == 'true'
    Path('output').mkdir(exist_ok=True)
    state = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}

    # Owner-authorized one-time Facebook design sample, checkpointed before sending.
    if not preview and 'facebook_design_sample_v1' not in state:
        state['facebook_design_sample_v1'] = {'status': 'unconfirmed'}
        save(state)
        sample = {'id': 'design_sample_v1', 'sample': True, 'published': now,
                  'title_si': 'පුවතේ වැදගත්ම තොරතුරු එකම තැනක',
                  'summary_si': 'ආදර්ශ පළ කිරීමකි.\n\nමෙය SL News 247 නව පුවත් සැලසුම පෙන්වීම සඳහා පළ කරන ආදර්ශයකි. රතු පසුබිම මත සුදු පැහැයෙන් සිරස්තලයත්, කහ පැහැයෙන් වැදගත් කොටසත් දක්වා තිබෙනවා.\n\nඉදිරි පුවත් සඳහා තහවුරු කළ කරුණු පැහැදිලි ඡේද ලෙස මෙහි ඇතුළත් කෙරෙනවා. මෙය සැබෑ සිද්ධියක් පිළිබඳ පුවතක් නොවේ.'}
        state['facebook_design_sample_v1'] = send_text('facebook', sample)
        save(state)

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
    report['editorial_update'] = share_editorial_update(state, articles, now, preview)
    Path('output/stories.json').write_text(json.dumps(selected, ensure_ascii=False, indent=2), encoding='utf-8')
    try:
        report['video'] = maybe_video(state, articles, now, preview)
    except Exception as exc:
        report['video'] = 'failed: ' + type(exc).__name__
    report['unconfirmed_headline_requests'] = sum(len(r.get('uncertain', {})) for r in state.get('stories', {}).values())
    report['selected_titles'] = [a['title_si'] for a in selected]
    if not preview:
        Path('data/source_health.json').write_text(json.dumps({'checked_at': now, 'configured_feeds': len(SOURCES), 'sources': health}, ensure_ascii=False, indent=2), encoding='utf-8')
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
