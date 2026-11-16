"""One bounded job with per-platform delivery checkpoints."""
import json
import os
from pathlib import Path
from config import OUTPUT_DIR, ASSET_DIR, USED_FILE
from news import get_best_news, make_script
from image import create_fallback
from voice import create_voice
from video import create_video
from utils import load_used, save_used

STATE = Path('data/delivery.json')

def checkpoint(state):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    temp = STATE.with_suffix('.tmp')
    temp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(STATE)

def main():
    for directory in (OUTPUT_DIR, ASSET_DIR):
        Path(directory).mkdir(parents=True, exist_ok=True)
    preview = os.getenv('PREVIEW_ONLY', 'false').lower() == 'true'
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    news = state.get('pending') or get_best_news()
    if not news:
        raise RuntimeError('No fresh translatable news available; no post created')
    if not preview:
        state['pending'] = news
        checkpoint(state)
    done = state.setdefault('delivered', {}).setdefault(news['id'], [])
    Path(OUTPUT_DIR, 'story.json').write_text(json.dumps(news, ensure_ascii=False, indent=2), encoding='utf-8')
    image = str(Path(ASSET_DIR, 'news.jpg'))
    voice = str(Path(ASSET_DIR, 'voice.mp3'))
    video = str(Path(OUTPUT_DIR, 'news.mp4'))
    create_fallback(image)
    if not create_voice(make_script(news), voice):
        raise RuntimeError('Sinhala voice generation failed')
    create_video(image, voice, news['title_si'], news['summary_si'], video)
    if not Path(video).exists() or Path(video).stat().st_size < 1000:
        raise RuntimeError('Video is missing or empty')
    if preview:
        print('Preview created; no uploads or delivery state changes')
        return
    from telegram import upload_news as telegram
    from facebook import upload_news as facebook
    from tiktok import upload_news as tiktok
    results = {}
    for name, upload in [('telegram', telegram), ('facebook', facebook), ('tiktok', tiktok)]:
        if name == 'tiktok' and os.getenv('TIKTOK_ENABLED', 'false').lower() != 'true':
            results[name] = 'blocked: authorization/public posting setup required'
            continue
        if name in done:
            results[name] = 'previously delivered'
            continue
        try:
            ok = upload(video, news)
        except Exception as exc:
            print(name, 'failed:', type(exc).__name__)
            ok = False
        results[name] = 'delivered' if ok else 'failed or pending; inspect platform before retry'
        if ok:
            done.append(name)
            checkpoint(state)
    required = ['telegram', 'facebook']
    if os.getenv('TIKTOK_ENABLED', 'false').lower() == 'true':
        required.append('tiktok')
    if all(name in done for name in required):
        used = load_used(USED_FILE)
        if news['id'] not in used:
            save_used(USED_FILE, used + [news['id']])
        state.pop('pending', None)
        state['delivered'] = dict(list(state['delivered'].items())[-1000:])
        checkpoint(state)
    Path(OUTPUT_DIR, 'delivery_report.json').write_text(json.dumps(results, indent=2))
    summary = os.getenv('GITHUB_STEP_SUMMARY')
    if summary:
        with open(summary, 'a') as handle:
            handle.write('## Sinhala news delivery\n' + '\n'.join(f'- {k}: {v}' for k, v in results.items()) + '\n')
    print(json.dumps(results))
    if any('failed' in value for value in results.values()):
        raise RuntimeError('One or more destinations did not confirm delivery')

if __name__ == '__main__':
    main()
