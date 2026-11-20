"""Merge scheduled-run delivery receipts with current remote GitHub state.

A different writer can update delivery records while the news job is running.
Never overwrite newer remote receipts or blindly repost unknown deliveries.
"""
import json
import sys
from pathlib import Path


def read(path, default):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return default


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def merge_state(remote, local):
    result = dict(remote)
    result['last_scan_at'] = max(remote.get('last_scan_at', 0), local.get('last_scan_at', 0))
    stories = dict(remote.get('stories', {}))
    for key, record in local.get('stories', {}).items():
        if key not in stories:
            stories[key] = record
            continue
        old = dict(stories[key])
        receipts = dict(old.get('receipts') or {})
        receipts.update(record.get('receipts') or {})
        uncertain = dict(old.get('uncertain') or {})
        uncertain.update(record.get('uncertain') or {})
        for destination in receipts:
            uncertain.pop(destination, None)
        old['receipts'] = receipts
        old['uncertain'] = uncertain
        old.setdefault('article', record.get('article'))
        # A rights-review hold must survive merging against the latest main
        # branch; without this, the queue disappears at the end of every scan.
        hold = record.get('photo_review')
        if hold and hold.get('at', 0) >= (old.get('photo_review') or {}).get('at', 0):
            old['photo_review'] = hold
        if 'telegram' in receipts and 'facebook' in receipts:
            old.pop('photo_review', None)
        stories[key] = old
    result['stories'] = stories
    # Preserve all non-headline production journals as well. Formerly only
    # 'stories' survived this merge, silently dropping video cooldowns,
    # official-video-link receipts and editorial history every run.
    for key in ('videos', 'bulletins', 'official_video_links', 'editorial_updates'):
        merged = dict(remote.get(key) or {})
        for article_id, local_entry in (local.get(key) or {}).items():
            if article_id not in merged:
                merged[article_id] = local_entry
                continue
            older = merged[article_id]
            if isinstance(older, dict) and isinstance(local_entry, dict):
                updated = {**older, **local_entry}
                if 'destinations' in older or 'destinations' in local_entry:
                    destinations = dict(older.get('destinations') or {})
                    for platform, incoming in (local_entry.get('destinations') or {}).items():
                        previous = destinations.get(platform)
                        # A stale worker must never overwrite a confirmed
                        # delivery with an unconfirmed/failed request.
                        successful = lambda value: (
                            value is True or value == 'accepted'
                            or isinstance(value, dict) and bool(value.get('id'))
                        )
                        if successful(previous) and not successful(incoming):
                            continue
                        destinations[platform] = incoming
                    updated['destinations'] = destinations
                merged[article_id] = updated
        result[key] = merged
    for key in ('last_video_at', 'last_bulletin_at'):
        result[key] = max(remote.get(key, 0), local.get(key, 0))
    for key in ('video_style', 'facebook_design_sample_v1'):
        if key in local and key not in result:
            result[key] = local[key]
    return result


def main(snapshot_dir):
    folder = Path(snapshot_dir)
    remote = read('data/sri_lanka_delivery.json', {})
    local = read(folder / 'sri_lanka_delivery.json', {})
    write('data/sri_lanka_delivery.json', merge_state(remote, local))

    health_remote = read('data/source_health.json', {})
    health_local = read(folder / 'source_health.json', {})
    if health_local.get('checked_at', 0) >= health_remote.get('checked_at', 0):
        write('data/source_health.json', health_local)

    remote_cache = read('data/translation_cache.json', {})
    local_cache = read(folder / 'translation_cache.json', {})
    if local_cache:
        write('data/translation_cache.json', {**local_cache, **remote_cache})

    remote_used = read('used.json', [])
    local_used = read(folder / 'used.json', [])
    if local_used:
        write('used.json', list(dict.fromkeys(remote_used + local_used))[-1000:])


if __name__ == '__main__':
    main(sys.argv[1])
