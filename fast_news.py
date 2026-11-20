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
    # Publisher-specific subject feeds capture stories missed by front-page RSS.
    ('Lankadeepa Sports', 'https://www.lankadeepa.lk/rss/sport/6'),
    ('Lankadeepa World', 'https://www.lankadeepa.lk/rss/world_news/14'),
    ('Lankadeepa Video News', 'https://www.lankadeepa.lk/rss/videos/12'),
    ('Lankadeepa National', 'https://www.lankadeepa.lk/rss/news/48'),
    ('Neth News', 'https://nethnews.lk/feed/'),
    ('Lanka Truth Sinhala', 'https://lankatruth.com/si/?feed=rss2'),
    ('Lankadeepa Politics', 'https://www.lankadeepa.lk/rss/politics/13'),
    ('Neth Sports', 'https://www.nethnews.lk/sports/feed/'),
    ('Neth International', 'https://www.nethnews.lk/international-news/feed/'),
    ('Neth Politics', 'https://www.nethnews.lk/politics/feed/'),
    ('Siyatha Sports', 'https://siyathanews.lk/archives/category/sports-news/feed'),
    ('Siyatha Business', 'https://siyathanews.lk/archives/category/business-news/feed'),
    ('Siyatha World', 'https://siyathanews.lk/archives/category/world-news/feed'),
    ('Lanka Truth World', 'https://lankatruth.com/si/?feed=rss2&cat=3'),
    ('Lanka Truth Economy', 'https://lankatruth.com/si/?feed=rss2&cat=5'),
    ('Lanka Truth Sport', 'https://lankatruth.com/si/?feed=rss2&cat=6'),
]
STATE_FILE = Path('data/sri_lanka_delivery.json')
# A missed GitHub schedule should not permanently lose yesterday's news.
MAX_AGE = 30 * 3600


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
    for item in feed.entries[:100]:
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
        from rss_video import rss_video_urls
        video_urls = rss_video_urls(item)
        article = {'id': fingerprint(title), 'title_si': title,
                   'summary_si': summary, 'link': link, 'source': source,
                   'published': published}
        if video_urls:
            article['rss_video_urls'] = video_urls
        articles.append(article)
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
    with ThreadPoolExecutor(max_workers=10) as pool:
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
    attribution = ('\n\n📷 සංකේතාත්මක ඡායාරූපයක්: Dhanuja Menaka / Wikimedia Commons (CC0). '
                   'මෙය රුවන්පුර අධිවේගී මාර්ගයේ ඉදිකිරීම් ස්ථානය නොවේ.'
                   if article.get('illustrative_photo') == 'sri_lanka_expressway_cc0' else '')
    from media import video_credit
    video_attribution = video_credit(article) if article.get('licensed_footage') else ''
    video_notice = ('\n\n🎬 මෙය Sinhala narration සහ graphic animation සහිත පුවත් සාරාංශයකි. '
                    'සිද්ධියේ සත්‍ය වීඩියෝ දර්ශන නොවේ.'
                    if article.get('animated_bulletin') else '')
    return f"🇱🇰 {title}\n\n{body}{attribution}{video_notice}{video_attribution}\n\n🕒 {stamp}\n━━━━━━━━━━━━\nSL NEWS 24/7"


def send_text(platform, article):
    if not article.get('sample') and not publishable(article):
        return {'error': 'missing_or_unrelated_story_details'}
    from pathlib import Path
    if article.get('sample'):
        return {'error': 'sample_posts_disabled'}
    try:
        from real_photo import select_real_photo
        photo_path, image_kind, credit = select_real_photo(article)
        if not photo_path:
            return {'error': 'real_photo_unavailable_review_required'}
        from image import news_card
        image_path = news_card(article, image_path=photo_path,
                               illustrative=(image_kind == 'licensed_context_photo'))
        if not image_path or not Path(image_path).is_file() or Path(image_path).stat().st_size < 1000:
            return {'error': 'real_photo_card_failed'}
    except Exception as exc:
        print('Real photo processing blocked:', type(exc).__name__, str(exc)[:160])
        return {'error': 'real_photo_processing_failed'}
    message = caption(article)
    if image_kind == 'licensed_context_photo':
        message += ('\n\n📷 සංකේතාත්මක සැබෑ ඡායාරූපයකි; මෙම සිද්ධියේ ඡායාරූපයක් නොවේ.'
                    + '\nඡායාරූපය: ' + credit['creator'] + ' / Wikimedia Commons'
                    + '\nබලපත්‍රය: ' + credit['license']
                    + '\nමූලාශ්‍රය: ' + credit['source']
                    + ('\nබලපත්‍ර සබැඳිය: ' + credit['license_url'] if credit['license_url'] else ''))
    if platform == 'telegram' and len(message) > 1024:
        return {'error': 'caption_too_long_review_required'}
    if platform == 'telegram':
        token, chat = os.getenv('TG_TOKEN'), os.getenv('TG_CHAT_ID')
        if not token or not chat:
            return {'error': 'missing_credentials'}
        with open(image_path, 'rb') as photo:
            response = requests.post(f'https://api.telegram.org/bot{token}/sendPhoto',
                                     data={'chat_id': chat, 'caption': message},
                                     files={'photo': photo}, timeout=(5, 45))
        data = response.json()
        if response.ok and data.get('ok'):
            return {'id': str(data['result']['message_id']), 'format': image_kind}
    else:
        page, token = os.getenv('FB_PAGE_ID'), os.getenv('FB_PAGE_TOKEN')
        if not page or not token:
            return {'error': 'missing_credentials'}
        with open(image_path, 'rb') as photo:
            response = requests.post(f'https://graph.facebook.com/v22.0/{page}/photos',
                                     data={'access_token': token, 'caption': message},
                                     files={'source': photo}, timeout=(5, 60))
        data = response.json()
        if response.ok and data.get('id'):
            return {'id': str(data.get('post_id') or data['id']), 'format': image_kind}
    return {'error': 'api_rejected', 'http': response.status_code,
            'code': data.get('error', {}).get('code')}


def deliver(state, articles, now, preview=False, sender=send_text):
    results = {name: {'sent': 0, 'failed': 0, 'uncertain': 0} for name in ('telegram', 'facebook')}
    records = state.setdefault('stories', {})
    limit = max(1, min(60, int(os.getenv('MAX_NEWS_PER_RUN', '30'))))
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


def maybe_animated_bulletin(state, articles, now, preview):
    """One clearly labelled, original moving Sinhala bulletin per 15 minutes.

    Source footage is never fabricated. Video delivery is checkpointed before
    external requests, so lost responses do not cause duplicate uploads.
    """
    if os.getenv('VIDEO_BULLETINS_ENABLED', 'true').lower() != 'true':
        return 'animated_bulletins_disabled'
    if not preview and now - state.get('last_bulletin_at', 0) < 900:
        return 'waiting_for_15_minute_bulletin_interval'
    history = state.setdefault('bulletins', {})
    from animated_bulletin import render_bulletin, narration_for
    # Skip a headline whose long/empty excerpt cannot be narrated completely.
    # Try the next eligible story, rather than failing the entire news video scan.
    candidate, path, failed = None, None, 0
    for article in articles:
        if (article['id'] in history
                # An older publisher-link receipt must not prevent a new
                # original Sinhala video for the same news story.
                or not publishable(article)
                or (not preview and not all(
                    dest in state.get('stories', {}).get(article['id'], {}).get('receipts', {})
                    for dest in ('telegram', 'facebook')))):
            continue
        if len(article.get('title_si','')) > 140:
            continue
        try:
            narration_for(article)
        except ValueError:
            continue
        try:
            path = render_bulletin(article)
            candidate = article
            break
        except ValueError as exc:
            failed += 1
            print('Bulletin skipped unsuitable article:', str(exc)[:150])
            if failed >= 12:
                break
        except Exception as exc:
            print('Animated bulletin unavailable:', type(exc).__name__, str(exc)[:150])
            return 'animated_bulletin_failed_' + type(exc).__name__
    if not candidate:
        return 'no_renderable_news_bulletin_candidate'
    if preview:
        return 'preview_animated_bulletin_created'
    # Store intent before an external API upload to avoid blind duplicates.
    history[candidate['id']] = {'at': now, 'status': 'started', 'destinations': {}}
    state['last_bulletin_at'] = now
    save(state)
    from telegram import upload_news as send_telegram
    from facebook import upload_news as send_facebook
    for platform, upload in (('telegram', send_telegram), ('facebook', send_facebook)):
        history[candidate['id']]['destinations'][platform] = 'unconfirmed'
        save(state)
        try:
            ok = upload(path, dict(candidate, animated_bulletin=True))
        except Exception as exc:
            print('Bulletin upload exception:', platform, type(exc).__name__)
            ok = False
        history[candidate['id']]['destinations'][platform] = (
            'accepted' if ok else 'unconfirmed_or_failed')
        save(state)
    destinations = history[candidate['id']]['destinations']
    history[candidate['id']]['status'] = (
        'delivered' if all(value == 'accepted' for value in destinations.values())
        else 'delivery_needs_review')
    save(state)
    return {'format': 'animated_news_bulletin_not_event_footage',
            'article_id': candidate['id'],
            'status': history[candidate['id']]['status'],
            'destinations': destinations}


def fallback_video(state, articles, now, preview):
    # A publisher video link does not count as our own uploaded bulletin.
    # Attempt both distinct formats, on different stories, with checkpoints.
    # Owner preference: deliver self-narrated SL NEWS bulletins, not links
    # promoting other broadcasters. Keep original source references internal.
    # External footage cannot be copied without verified rights.
    linked = ('official_video_links_disabled'
              if os.getenv('SHARE_OFFICIAL_VIDEO_LINKS', 'false').lower() != 'true'
              else share_official_video(state, articles, now, preview))
    bulletin = maybe_animated_bulletin(state, articles, now, preview)
    if isinstance(linked, str) and linked == 'skipped_no_verified_event_video_or_official_link':
        return bulletin
    if linked == 'official_video_links_disabled':
        return bulletin
    if isinstance(bulletin, str) and bulletin in (
            'no_new_verified_story_for_bulletin',
            'waiting_for_15_minute_bulletin_interval',
            'animated_bulletins_disabled'):
        return linked
    return {'official_source_video': linked, 'original_animated_bulletin': bulletin}


def maybe_video(state, articles, now, preview):
    if not articles:
        return 'no_fresh_story'
    if not preview and now - state.get('last_video_at', 0) < 900 and state.get('video_style') == 'real-footage-v1':
        return fallback_video(state, articles, now, preview)
    recent = state.setdefault('videos', {})
    candidate = next((a for a in articles if a['id'] not in recent), None)
    if not candidate:
        return fallback_video(state, articles, now, preview)
    from media import choose_video
    from editorial import brief_for
    candidate = None
    footage = None
    for article in articles:
        if article['id'] in recent:
            continue
        if not brief_for(article):
            continue
        try:
            footage = choose_video(article)
        except Exception as exc:
            print('Licensed footage unavailable for article:', article['id'], type(exc).__name__)
            continue
        if footage:
            candidate = article
            break
    if not candidate:
        return fallback_video(state, articles, now, preview)
    from video import create_footage_video
    video = 'output/news.mp4'
    from voice import create_voice
    brief = brief_for(candidate)
    audio = 'output/news_narration.mp3'
    Path(audio).unlink(missing_ok=True)
    if not create_voice(brief['body_si'], audio):
        print('Licensed-footage voice unavailable; falling back to original bulletin')
        return fallback_video(state, articles, now, preview)
    # Ad intervals are explicit newsroom-reviewed cuts for licensed footage only.
    # Never hide or replace the source watermark/required attribution.
    registry_path = Path('data/verified_event_media.json')
    registry = json.loads(registry_path.read_text(encoding='utf-8')) if registry_path.exists() else {}
    clip_record = registry.get(candidate['id'], {}).get('video', {})
    # Automatically locate potential ad breaks for a newsroom review report.
    # Detection must not silently remove genuine footage.
    try:
        from ad_detector import detect_ad_candidates
        detect_ad_candidates(footage, 'output/ad_review_' + candidate['id'] + '.json')
    except Exception as exc:
        print('Ad analysis unavailable:', type(exc).__name__)
    if (clip_record.get('ad_segments_reviewed') is True
            and clip_record.get('ad_segments')):
        from video import trim_reviewed_ad_segments
        trimmed = 'output/reviewed_event_footage.mp4'
        footage = trim_reviewed_ad_segments(
            footage, trimmed, clip_record['ad_segments'], reviewed=True)
    try:
        create_footage_video(footage, candidate['title_si'], candidate['summary_si'], video, audio_path=audio)
    except Exception as exc:
        print('Licensed-footage editing unavailable; falling back to original bulletin:', type(exc).__name__)
        return fallback_video(state, articles, now, preview)
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
        # Record intent before the request. An ambiguous API response must
        # not cause a blind retry and duplicate real-event footage.
        recent[candidate['id']]['destinations'][name] = 'unconfirmed'
        save(state)
        try:
            ok = publish(video, dict(candidate, licensed_footage=True))
        except Exception as exc:
            print('Licensed video upload unconfirmed:', name, type(exc).__name__)
            ok = False
        recent[candidate['id']]['destinations'][name] = 'accepted' if ok else 'unconfirmed_or_failed'
        save(state)
    receipts = recent[candidate['id']]['destinations']
    recent[candidate['id']]['status'] = (
        'delivered' if all(value == 'accepted' for value in receipts.values())
        else 'delivery_needs_review')
    save(state)
    return {'format': 'licensed_event_footage', **recent[candidate['id']]}


def send_official_video_link(platform, article, url):
    """Send a real publisher video link with preview; never upload its footage."""
    from publisher_videos import youtube_watch
    verified_url = youtube_watch(url)
    if not verified_url:
        return {'error': 'invalid_official_video_url'}
    message = caption(article) + '\n\n🎥 මුල් පුවත් වීඩියෝව: ' + verified_url
    if platform == 'telegram':
        token, chat = os.getenv('TG_TOKEN'), os.getenv('TG_CHAT_ID')
        if not token or not chat:
            return {'error': 'missing_credentials'}
        response = requests.post(
            f'https://api.telegram.org/bot{token}/sendMessage',
            json={'chat_id': chat, 'text': message,
                  'link_preview_options': {'is_disabled': False}}, timeout=(5, 30))
        data = response.json()
        if response.ok and data.get('ok'):
            return {'id': str(data['result']['message_id']), 'format': 'official_video_link'}
    elif platform == 'facebook':
        page, token = os.getenv('FB_PAGE_ID'), os.getenv('FB_PAGE_TOKEN')
        if not page or not token:
            return {'error': 'missing_credentials'}
        response = requests.post(
            f'https://graph.facebook.com/v22.0/{page}/feed',
            data={'access_token': token, 'message': message, 'link': verified_url},
            timeout=(5, 45))
        data = response.json()
        if response.ok and data.get('id'):
            return {'id': str(data['id']), 'format': 'official_video_link'}
    else:
        return {'error': 'unsupported_destination'}
    return {'error': 'api_rejected', 'http': response.status_code}


def share_official_video(state, articles, now, preview):
    """Share only a verified exact-article original publisher player URL."""
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
                result = send_official_video_link(name, linked, url)
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

    # No demo/sample posts: only verified real stories with reviewed photos.
    articles, health = collect(now)
    # Keep receipts long enough to suppress repeats after delayed schedules.
    state['stories'] = {key: val for key, val in state.get('stories', {}).items()
                        if now - val['article']['published'] < 7 * 24 * 3600}
    state['videos'] = {key: val for key, val in state.get('videos', {}).items()
                       if now - val['at'] < 7 * 24 * 3600}
    report = {'preview': preview, 'feeds': health, 'fresh_unique_articles': len(articles),
              'configured_feeds': len(SOURCES),
              'working_feeds': sum(h.get('http') == 200 for h in health),
              'failed_feeds': [h['source'] for h in health if h.get('http') != 200],
              'publishable_articles': sum(publishable(a) for a in articles),
              'tiktok': 'enabled' if os.getenv('TIKTOK_ENABLED', 'false').lower() == 'true' else 'blocked_authorization_required'}
    # Find actual incident video links for permission review, without copying
    # broadcaster footage or treating a public URL as a reuse license.
    try:
        from footage_discovery import discover_candidates
        report['footage_discovery'] = discover_candidates(articles)
    except Exception as exc:
        report['footage_discovery'] = {'status': 'unavailable', 'error': type(exc).__name__}
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
    # Report independent video results, not just a green workflow status.
    video_result = report['video']
    animated = (video_result.get('original_animated_bulletin', video_result)
                if isinstance(video_result, dict) else video_result)
    report['original_video_upload_ok'] = (
        isinstance(animated, dict)
        and animated.get('format') == 'animated_news_bulletin_not_event_footage'
        and all(v == 'accepted' for v in animated.get('destinations', {}).values())
        and len(animated.get('destinations', {})) == 2
    )
    report['selected_titles'] = [a['title_si'] for a in selected]
    # Explicit publishing diagnostics, so a green CI badge is not confused
    # with evidence that fresh posts or original video were actually sent.
    report['publishing_status'] = {
        'new_photo_posts': {dest: delivery[dest]['sent'] for dest in ('telegram','facebook')},
        'fresh_publishable_found': report['publishable_articles'],
        'not_new_or_already_delivered': max(0, report['publishable_articles'] - len(selected)),
        'video_result': report['video'],
        'next_video_minimum_interval_minutes': 15,
        'note': 'Scheduled GitHub Actions are best effort, not a 5-minute SLA.',
    }

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
    licensed_video_failed = (
        isinstance(video_result, dict)
        and video_result.get('format') == 'licensed_event_footage'
        and video_result.get('status') != 'delivered'
    )
    video_issue = (
        licensed_video_failed
        or isinstance(animated, str) and animated.startswith(('failed:', 'animated_bulletin_failed_'))
        or isinstance(animated, dict)
        and animated.get('format') == 'animated_news_bulletin_not_event_footage'
        and not report['original_video_upload_ok']
    )
    if (report['unconfirmed_headline_requests']
            or any(v['failed'] or v['uncertain'] for v in delivery.values())
            or video_issue):
        raise RuntimeError('News delivery or original bulletin upload needs inspection')


if __name__ == '__main__':
    main()
