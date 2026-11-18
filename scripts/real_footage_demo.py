"""Licensed genuine moving-footage demonstration. Not a current news incident.
Source: Cherubino, Pattipola train.webm, Wikimedia Commons, CC BY-SA 3.0.
"""
import json
import subprocess
from pathlib import Path
import requests
from gtts import gTTS

OUTPUT = Path('output/real_footage_demo')
SOURCE = ('https://upload.wikimedia.org/wikipedia/commons/'
          '2/2b/Pattipola_train.webm')
FALLBACK = 'https://interactive-examples.mdn.mozilla.net/media/cc0-videos/flower.mp4'
# Never misrepresent historic footage as current breaking news.
NARRATION = (
    'මේ දැක්වෙන්නේ ශ්‍රී ලංකාවේ පට්ටිපොළ දුම්රිය ස්ථානයේ '
    'පැරණි සැබෑ වීඩියෝ දර්ශනයි. '
    'මුල් වීඩියෝවේ ශබ්දය සම්පූර්ණයෙන් ඉවත් කර, '
    'ඒ වෙනුවට සිංහල හඬක් එකතු කළ ආදර්ශයකි.'
)
FALLBACK_NARRATION = (
    'මේ සැබෑ මල් වීඩියෝ දර්ශනයේ මුල් ශබ්දය ඉවත් කර තිබෙනවා. '
    'ඒ වෙනුවට සිංහල හඬක් එකතු කළ වීඩියෝ සංස්කරණ ආදර්ශයක් මෙයයි.'
)

def run(args, timeout=120):
    return subprocess.run(args, check=True, timeout=timeout,
                          text=True, capture_output=True)

def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    # Prefer real Sri Lanka train footage. Wikimedia rate-limits CI
    # downloads, so use a genuine public-domain CC0 moving-video fallback.
    try:
        response = requests.get(SOURCE, timeout=(8, 60),
                                headers={'User-Agent': 'SLNews247-demo/1.0'})
        response.raise_for_status()
        source_url, script = SOURCE, NARRATION
        credit = ('Original creator: Cherubino\\n'
                  'Source: https://commons.wikimedia.org/wiki/File:Pattipola_train.webm\\n'
                  'License: CC BY-SA 3.0\\n'
                  'https://creativecommons.org/licenses/by-sa/3.0/\\n')
        extension = '.webm'
    except requests.RequestException as exc:
        print('Train footage source unavailable, using licensed CC0 flower demo:',
              type(exc).__name__)
        response = requests.get(FALLBACK, timeout=(8, 60))
        response.raise_for_status()
        source_url, script = FALLBACK, FALLBACK_NARRATION
        credit = ('Source: MDN CC0 Videos - Flower\\n'
                  'https://interactive-examples.mdn.mozilla.net/media/cc0-videos/flower.mp4\\n'
                  'License: CC0 (public domain dedication)\\n')
        extension = '.mp4'
    if len(response.content) < 100000 or len(response.content) > 20000000:
        raise RuntimeError('Source footage unexpected size')
    clip = OUTPUT / ('downloaded_original' + extension)
    clip.write_bytes(response.content)
    probe = run(['ffmpeg', '-v', 'error', '-i', str(clip),
                 '-f', 'null', '-'], timeout=80)
    voice = OUTPUT / 'sinhala_voice.mp3'
    gTTS(text=script, lang='si', slow=False).save(str(voice))
    from mutagen.mp3 import MP3
    audio_seconds = MP3(str(voice)).info.length
    if not 3 < audio_seconds < 45:
        raise RuntimeError('Unexpected narration duration')
    # 22-second real moving footage: retain only frames from source; no still-photo
    # substitutes and do not repeat or loop video. Muting original audio is
    # enforced by selecting ONLY the new input's audio stream.
    target = OUTPUT / 'SL_NEWS_247_REAL_FOOTAGE_SINHALA_VOICE.mp4'
    run(['ffmpeg', '-y', '-loglevel', 'error',
         '-i', str(clip), '-i', str(voice),
         '-filter_complex',
         '[0:v]scale=720:1280:force_original_aspect_ratio=decrease,'
         'pad=720:1280:(ow-iw)/2:(oh-ih)/2:color=black,'
         'fps=25,format=yuv420p[v]',
         '-map', '[v]', '-map', '1:a:0', '-t', '21',
         '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '25',
         '-c:a', 'aac', '-b:a', '128k', '-movflags', '+faststart',
         '-shortest', str(target)], timeout=150)
    if target.stat().st_size < 50000:
        raise RuntimeError('Output MP4 is unexpectedly small')
    run(['ffmpeg', '-v', 'error', '-i', str(target),
         '-f', 'null', '-'], timeout=70)
    notice = (
        'SL NEWS 24/7 - REAL MOVING FOOTAGE DEMONSTRATION ONLY\\n'
        'This is an editing demo, NOT current news and NOT footage of a news incident.\\n'
        + credit
        + 'Changes: Original audio removed; new Sinhala narration added; '
        'resized/re-encoded for vertical presentation.\\n'
        + 'If the train footage was used, provide CC BY-SA attribution with any repost.\\n')
    (OUTPUT / 'SOURCE_AND_LICENSE.txt').write_text(notice, encoding='utf-8')
    print(json.dumps({'status':'success','source_bytes':len(response.content),
                      'narration_seconds':round(audio_seconds,2),
                      'output_bytes':target.stat().st_size,
                      'original_sound':'muted','new_voice':'Sinhala',
                      'file':str(target)}, ensure_ascii=False))

if __name__ == '__main__':
    main()
