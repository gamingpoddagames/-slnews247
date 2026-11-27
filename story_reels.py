"""Per-story SL News 24/7 reel delivery, using existing renderer and accounts.

Each approved story gets its normal image post plus a video with the same
brand. Never insert unrelated event footage. Pending reels remain in the queue
across scans; uncertain API uploads are NOT blindly duplicated.
"""
import os
from pathlib import Path


def _approved_asset_attribution(article, kind):
    """Required media licence credit only; never general news-source boilerplate."""
    import json
    from media import REGISTRY
    if not REGISTRY.exists():
        return ''
    try:
        registry = json.loads(REGISTRY.read_text(encoding='utf-8'))
        entry = registry.get(article.get('id'), {})
        asset = entry.get(kind) if kind in entry else (
            entry if kind == 'photo' else {})
    except (OSError, ValueError, AttributeError):
        return ''
    if not isinstance(asset, dict) or asset.get('attribution_required') is not True:
        return ''
    if not all(asset.get(key) for key in
               ('creator', 'license', 'license_url', 'source_page')):
        raise ValueError('Licensed news media requires visible credit')
    symbol = '🎬' if kind == 'video' else '📷'
    return ('\n\n' + symbol + ' ' + asset['creator'] + ' · ' + asset['license']
            + ' (edited for news). ' + asset['source_page']
            + ' ' + asset['license_url'])


def _media_attribution(article):
    """Keep compulsory CC photo credit, omit optional source/about-image prose."""
    from real_photo import select_real_photo
    try:
        _, kind, credit = select_real_photo(article)
    except Exception as exc:
        print('Reel media lookup:', type(exc).__name__)
        return ''
    if kind in ('verified_institution_photo', 'verified_education_context_photo', 'verified_named_subject_photo') and credit:
        return ('\n\n📷 ' + credit['creator'] + ', ' + credit['license']
                + ' (cropped/resized). ' + credit['source']
                + ' ' + credit['license_url'])
    if kind == 'verified_event_photo':
        return _approved_asset_attribution(article, 'photo')
    if kind == 'verified_event_video_frame':
        from media import video_credit
        return video_credit(article)
    return ''


def render_story_reel(article, path):
    """Prioritize verified reusable real footage; otherwise animate real photos
    or original graphics with the existing consistent Sinhala reel renderer.
    """
    from animated_bulletin import render_bulletin, narration_for
    from media import choose_video
    article = dict(article, require_event_media=True)
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
    from media import choose_photo
    if not choose_photo(article):
        raise ValueError('Verified event media required; no graphic-only reel')
    return render_bulletin(article, path), 'verified_event_photo_reel'


def _render_reel(article, video_path):
    """Use authorised same-event footage if available, otherwise our own reel."""
    from animated_bulletin import render_bulletin, render_graphic_reel, narration_for
    strict = os.getenv('REELS_REQUIRE_EVENT_MEDIA', 'false').lower() == 'true'
    article = dict(article, require_event_media=strict)
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
    # A verified event photograph is a photo reel, never labelled as live footage.
    from media import choose_photo
    exact = choose_photo(article)
    if not exact and strict:
        raise ValueError('No verified event photo available for photo reel')
    try:
        return render_bulletin(article, video_path), ('verified_event_photo_reel' if exact else 'original_news_reel')
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
        if article.get('id') in journal or not publishable(article):
            continue
        record = state.get('stories', {}).get(article['id'], {})
        receipts = record.get('receipts', {})
        if not all(receipts.get(p, {}).get('id')
                   for p in ('telegram', 'facebook')):
            continue
        # News reported earlier today can be published for the first time
        # after reel rollout. Use its NEW primary-post delivery receipt as
        # eligibility, without backfilling every already-posted old story.
        new_primary_delivery = any(
            receipts.get(p, {}).get('at', 0) >= since
            for p in ('telegram', 'facebook'))
        if article.get('published', 0) < since and not new_primary_delivery:
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
    # Prioritize current news and avoid rechecking unavailable media every scan.
    # Keep older records for audit; never replay stale stories automatically.
    from fast_news import MAX_AGE
    pending = [(k, v) for k, v in pending
               if 0 <= now - v['article'].get('published', 0) <= MAX_AGE
               and (os.getenv('REELS_REQUIRE_EVENT_MEDIA', 'false').lower() != 'true'
                    or v.get('media_status') != 'awaiting_verified_event_media'
                    or now - v.get('last_attempt_at', 0) >= 900)]
    pending.sort(key=lambda item: (item[1]['article'].get('published', 0), item[0]),
                 reverse=True)
    status['pending'] = len(pending)
    if preview:
        return status

    strict = os.getenv('REELS_REQUIRE_EVENT_MEDIA', 'false').lower() == 'true'
    for story_id, entry in pending:
        if status['rendered'] >= max_per_run:
            break
        article = entry['article']
        from media import choose_photo, choose_video
        try:
            has_media = bool(choose_video(article) or choose_photo(article))
        except Exception:
            has_media = False
        if not has_media and strict:
            entry['last_attempt_at'] = now
            entry['media_status'] = 'awaiting_verified_event_media'
            save(state)
            continue
        entry.pop('media_status', None)
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
        attribution = (_approved_asset_attribution(article, 'video')
                       if format_name == 'approved_exact_event_clip'
                       else _media_attribution(article))
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
        r.get('status') in ('queued', 'render_failed')
        and 0 <= now - r.get('article', {}).get('published', 0) <= MAX_AGE
        for r in journal.values())
    return status

