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


def _render_reel(article, video_path):
    """Use authorised same-event footage if available, otherwise our own reel."""
    from animated_bulletin import render_bulletin, render_graphic_reel, narration_for
    try:
        from media import choose_video
        clip = choose_video(article)
        if clip:
            from video import create_footage_video
            from voice import create_voice
            audio = str(Path(video_path).with_suffix('.mp3'))
            if create_voice(narration_for(article), audio):
                if create_footage_video(clip, article['title_si'],
                                        article.get('summary_si', ''),
                                        video_path, audio_path=audio):
                    return video_path, 'approved_exact_event_clip'
    except Exception as exc:
        print('Approved reel clip unavailable; using branded graphics:',
              type(exc).__name__)
    try:
        return render_bulletin(article, video_path), 'branded_sinhala_voice_reel'
    except Exception as exc:
        print('Voice reel unavailable; using original motion graphic:',
              type(exc).__name__)
    return render_graphic_reel(article, video_path), 'branded_graphic_reel'


def publish_reels(state, articles, now, preview=False, max_per_run=None):
    """Durable one-reel-per-story queue for existing Facebook and Telegram accounts.

    Each eligible story has already passed the article and primary-post gates.
    Render errors can retry, while uncertain external uploads require inspection.
    """
    from fast_news import publishable, save, caption
    from telegram import upload_video as telegram_video
    from facebook import upload_video as facebook_video
    max_per_run = (max_per_run if max_per_run is not None
                   else int(os.getenv('MAX_REELS_PER_RUN', '2')))
    max_per_run = max(1, min(3, max_per_run))
    journal = state.setdefault('reels', {})
    # Rollout boundary avoids an initial blast of weeks-old video duplicates.
    since = state.get('reels_started_at', now - 600)
    if not preview:
        state.setdefault('reels_started_at', since)
    status = {'rendered': 0, 'sent': {'telegram': 0, 'facebook': 0},
              'failed_or_uncertain': 0, 'pending': 0, 'stories': []}
    queued = []

    for article in articles:
        if (article.get('id') in journal or not publishable(article)
                or article.get('published', 0) < since):
            continue
        record = state.get('stories', {}).get(article['id'], {})
        if not all(record.get('receipts', {}).get(p, {}).get('id')
                   for p in ('telegram', 'facebook')):
            continue
        # Previously completed original bulletin is a real uploaded video;
        # do not post another near-identical reel about the same news item.
        prior = (state.get('bulletins') or {}).get(article['id'], {})
        already = all((prior.get('destinations') or {}).get(p) == 'accepted'
                      for p in ('telegram', 'facebook'))
        if not preview:
            journal[article['id']] = {
                'at': now, 'article': article,
                'status': 'delivered_earlier' if already else 'queued',
                'destinations': ({'telegram': 'accepted', 'facebook': 'accepted'}
                                 if already else {})
            }
        elif not already:
            queued.append((article['id'], {'article': article, 'status': 'queued',
                                            'destinations': {}, 'at': now}))
    if not preview:
        save(state)

    # Queue is independent of the fresh RSS window: a story still gets its reel
    # even if a later GitHub scan does not find the article in the feed.
    pending = ([(k, v) for k, v in journal.items()
                if v.get('status') in ('queued', 'render_failed')
                and (v.get('status') != 'render_failed'
                     or now - v.get('last_attempt_at', 0) >= 900)]
               if not preview else queued)
    pending.sort(key=lambda item: (item[1]['article'].get('published', 0), item[0]))
    status['pending'] = len(pending)
    if preview:
        return status

    for story_id, entry in pending[:max_per_run]:
        article = entry['article']
        status['stories'].append(story_id)
        video_path = str(Path('output') / 'reels' / (story_id + '.mp4'))
        Path(video_path).parent.mkdir(parents=True, exist_ok=True)
        try:
            path, format_name = _render_reel(article, video_path)
        except Exception as exc:
            entry['status'] = 'render_failed'
            entry['last_attempt_at'] = now
            entry['last_error'] = type(exc).__name__
            status['failed_or_uncertain'] += 1
            save(state)
            continue
        status['rendered'] += 1
        entry.update(status='upload_started', format=format_name,
                     last_attempt_at=now)
        save(state)
        attribution = (_media_attribution(article)
                       if format_name != 'approved_exact_event_clip' else '')
        normal = caption(article)
        # Telegram video captions have a 1024-character limit. Do not cut
        # off the mandatory licence details; shorten the news summary instead.
        if attribution and len(normal + attribution) > 1024:
            normal_tg = '🔴 ' + article['title_si'] + '\n\nSL NEWS 24/7'
        else:
            normal_tg = normal
        for platform, uploader, message in (
            ('telegram', telegram_video, normal_tg + attribution),
            ('facebook', facebook_video, normal + attribution),
        ):
            if entry['destinations'].get(platform):
                continue
            entry['destinations'][platform] = 'unconfirmed'
            save(state)
            try:
                ok = bool(uploader(path, message))
            except Exception as exc:
                print('Reel delivery issue:', platform, type(exc).__name__)
                ok = False
            entry['destinations'][platform] = (
                'accepted' if ok else 'unconfirmed_or_failed')
            if ok:
                status['sent'][platform] += 1
            else:
                status['failed_or_uncertain'] += 1
            save(state)
        entry['status'] = (
            'delivered' if all(entry['destinations'].get(p) == 'accepted'
                               for p in ('telegram', 'facebook'))
            else 'delivery_needs_review')
        save(state)

    status['pending'] = sum(
        r.get('status') in ('queued', 'render_failed') for r in journal.values())
    return status
