"""Per-story SL News 24/7 reel delivery, using existing renderer and accounts.

Each approved story gets its normal image post plus a video with the same
brand. Never insert unrelated event footage. Pending reels remain in the queue
across scans; uncertain API uploads are NOT blindly duplicated.
"""
import os
from pathlib import Path


def _media_attribution(article):
    """Only mandatory Creative Commons terms appear publicly.

    The full discovery records stay in the internal newsroom journals.
    """
    from real_photo import select_real_photo
    try:
        _, kind, credit = select_real_photo(article)
    except Exception as exc:
        print('Reel media lookup:', type(exc).__name__)
        return ''
    if kind != 'verified_institution_photo' or not credit:
        return ''
    return ('\n\n📷 ' + credit['label_si'] + ' — '
            + credit['creator'] + ', ' + credit['license']
            + ' (cropped/resized). ' + credit['source']
            + ' ' + credit['license_url'])


def render_story_reel(article, path):
    """Prioritize verified reusable real footage; otherwise animate real photos
    or original graphics with the existing consistent Sinhala reel renderer.
    """
    from animated_bulletin import render_bulletin, narration_for
    from media import choose_video
    try:
        footage = choose_video(article)
    except Exception as exc:
        print('Approved event clip unavailable:', type(exc).__name__)
        footage = None
    if footage:
        from voice import create_voice
        from video import create_footage_video
        narration_path = str(Path(path).with_suffix('.mp3'))
        try:
            if not create_voice(narration_for(article), narration_path):
                raise RuntimeError('Narration synthesis unavailable')
            create_footage_video(footage, article['title_si'], '',
                                 path, audio_path=narration_path)
            return path, 'verified_event_clip'
        except Exception as exc:
            print('Licensed event footage edit unavailable; using branded reel:',
                  type(exc).__name__)
    return render_bulletin(article, path), 'original_graphic_or_verified_photo'


def publish_reels(state, articles, now, preview=False, max_per_run=None):
    """Progress persistent per-story reel queue after photo delivery.

    A clean branded graphic+Sinhala-voice reel is rendered when there is no
    licensed matching photo/video. This is not a guarantee of API acceptance.
    """
    from fast_news import publishable, save, caption
    from animated_bulletin import narration_for
    from telegram import upload_video as telegram_video
    from facebook import upload_video as facebook_video
    max_per_run = (max_per_run if max_per_run is not None
                   else int(os.getenv('MAX_REELS_PER_RUN', '1')))
    max_per_run = max(1, min(3, max_per_run))
    journal = state.setdefault('reels', {})
    status = {'rendered': 0, 'sent': {'telegram': 0, 'facebook': 0},
              'failed_or_uncertain': 0, 'pending': 0, 'stories': []}
    targets = []
    # Process newest stories with a successful primary photo/graphic post,
    # but allow gradual reel catch-up for previously published stories.
    for article in articles:
        if not publishable(article):
            continue
        record = state.get('stories', {}).get(article['id'], {})
        if not all(name in record.get('receipts', {})
                   for name in ('telegram', 'facebook')):
            continue
        existing = journal.get(article['id'])
        if existing:
            continue
        try:
            narration_for(article)
        except ValueError:
            continue
        targets.append(article)
        if len(targets) >= max_per_run:
            break
    status['pending'] = sum(
        a['id'] not in journal and publishable(a)
        and all(p in state.get('stories', {}).get(a['id'], {}).get('receipts', {})
                for p in ('telegram', 'facebook'))
        for a in articles
    )
    for article in targets:
        status['stories'].append(article['id'])
        if preview:
            continue
        video_path = str(Path('output') / 'reels' / (article['id'] + '.mp4'))
        try:
            path, reel_mode = render_story_reel(article, video_path)
        except Exception as exc:
            status['failed_or_uncertain'] += 1
            print('Reel rendering error:', article['id'], type(exc).__name__)
            # Retry rendering safely next scan: no API request was made.
            continue
        status['rendered'] += 1
        # Persist before external calls. An ambiguous response needs human
        # inspection; never send a duplicate reel automatically.
        journal[article['id']] = {'at': now, 'status': 'upload_started',
                                  'mode': reel_mode, 'destinations': {}}
        save(state)
        attribution = (_media_attribution(article)
                       if reel_mode != 'verified_event_clip'
                       else __import__('media').video_credit(article))
        if attribution and len(caption(article) + attribution) > 1024:
            # Keep CC credits intact; trim only the factual summary for TG.
            title = article['title_si']
            tg_caption = '🔴 ' + title + '\n\nSL NEWS 24/7' + attribution
        else:
            tg_caption = caption(article) + attribution
        fb_caption = caption(article) + attribution
        for destination, uploader, message in (
            ('telegram', telegram_video, tg_caption),
            ('facebook', facebook_video, fb_caption),
        ):
            journal[article['id']]['destinations'][destination] = 'unconfirmed'
            save(state)
            try:
                ok = bool(uploader(path, message))
            except Exception as exc:
                print('Reel delivery issue:', destination, type(exc).__name__)
                ok = False
            journal[article['id']]['destinations'][destination] = (
                'accepted' if ok else 'unconfirmed_or_failed')
            if ok:
                status['sent'][destination] += 1
            else:
                status['failed_or_uncertain'] += 1
            save(state)
        result = journal[article['id']]['destinations']
        journal[article['id']]['status'] = (
            'delivered' if all(v == 'accepted' for v in result.values())
            else 'delivery_needs_review')
        save(state)
    return status
