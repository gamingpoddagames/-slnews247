"""Original, clearly labelled animated Sinhala news bulletin, not event footage.

Uses verified news text, Sinhala TTS and our own graphic. It neither copies
broadcast clips nor purports to show the actual incident.
"""
import json
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def narration_for(article):
    from fast_news import complete_sentences, relevant_summary
    title = article.get('title_si', '').strip()
    # Prefer reviewed, fully sourced editorial detail rather than a short RSS
    # teaser. Use original Sinhala wording, not the publisher's voice/audio.
    from editorial import brief_for
    reviewed = brief_for(article) if article.get('id') and article.get('link') else {}
    source_text = reviewed.get('body_si') or article.get('summary_si', '')
    summary = complete_sentences(source_text, 1250)
    if not summary or not relevant_summary(title, summary):
        raise ValueError('Factual, matching Sinhala narration required')
    clauses = []
    for sentence in __import__('re').findall(r'[^.!?।]+[.!?।]+', summary):
        if len(' '.join(clauses + [sentence])) > 580:
            break
        clauses.append(sentence.strip())
    if not clauses:
        raise ValueError('No complete, suitably short narration sentence')
    return title + '. ' + ' '.join(clauses)


def _story_facts(article, narration):
    """Display three DIFFERENT complete factual sentences about this story."""
    from story_visual import story_facts
    facts = story_facts(article)
    return (facts + [article['title_si']] * 3)[:3]


def _slide(article, text, index, image_path, destination, photo_label=None):
    """Three intentionally different broadcast scenes; no fabricated event shots."""
    from image import draw_mixed, fit_headline, cover_resize, latin_font
    from PIL import ImageOps
    import re
    from datetime import datetime
    from zoneinfo import ZoneInfo

    W, H = 720, 1280
    palette = [('#071329', '#123966', '#f9bc39')] * 3
    bg, accent, highlight = palette[index]
    canvas = Image.new('RGB', (W, H), bg)
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, 0, W, 19), fill=highlight)
    draw.rounded_rectangle((35, 44, 685, 117), radius=22, fill=accent)
    draw.text((58, 65), 'SL NEWS 24/7', font=latin_font(34, bold=True), fill='white')
    draw.rounded_rectangle((35, 144, 205, 191), radius=12, fill='#a9223c')
    draw.text((53, 151), 'NEWS  /  0' + str(index+1),
              font=latin_font(21, bold=True), fill='white')

    # Only verified licensed exact-event media may fill the video window.
    # Without one, animate original editorial facts, never unrelated stock.
    if image_path:
        with Image.open(image_path) as source:
            shot = ImageOps.fit(source.convert('RGB'), (650, 520),
                                method=Image.Resampling.LANCZOS)
        canvas.paste(shot, (35, 210))
        draw = ImageDraw.Draw(canvas)
    else:
        # Display the actual article's topic, numeric detail and sourced fact
        # as a prominent moving infographic, never an unrelated stock image.
        from story_visual import draw_story_hero
        draw_story_hero(canvas, article, (35, 210, 685, 735), scene=index,
                        fact=text)
        draw = ImageDraw.Draw(canvas)

    headline = re.sub(r'\s*\((?:VIDEO|වීඩියෝ)\)', '',
                      article.get('title_si', ''), flags=re.I)
    draw.rounded_rectangle((35, 758, 685, 1029), radius=25, fill='#101d37')
    size, lines, step = fit_headline(draw, headline, width=570,
                                      max_height=227, start_size=40, min_size=20)
    baseline = 820
    for line in lines:
        draw_mixed(draw, (68, baseline), line, size, bold=True, fill='white')
        baseline += step

    # Fact line as a lower-third; fit or omit, never cut off characters.
    draw.rectangle((0, 1055, W, H), fill='#06132a')
    draw.line((37, 1058, 683, 1058), fill=highlight, width=5)
    try:
        size, lines, step = fit_headline(draw, text, width=622,
                                         max_height=137, start_size=26, min_size=18)
        baseline = 1118
        for line in lines:
            draw_mixed(draw, (48, baseline), line, size, fill='#f4f7fb')
            baseline += step
    except ValueError:
        # The full fact is still narrated and in the post text.
        pass
    # Brand and factual news only; archive institution imagery is identified
    # by its subject in the picture, not misrepresented as event footage.
    if image_path and photo_label:
        draw_mixed(draw, (44, 1241), photo_label, 18, fill='#a6bed1')
    canvas.save(destination)
    return str(destination)


def build_scene_images(article, script, directory):
    """Create distinct slides; reuse one exact-event photo only if licensed."""
    from real_photo import select_real_photo
    folder = Path(directory)
    folder.mkdir(parents=True, exist_ok=True)
    try:
        image_path, image_kind, credit = select_real_photo(article)
    except Exception as exc:
        print('Bulletin photo unavailable, using original information scenes:',
              type(exc).__name__)
        image_path, image_kind, credit = None, None, None
    if __import__('os').getenv('REELS_REQUIRE_EVENT_MEDIA', 'false').lower() == 'true':
        if not image_path or image_kind != 'verified_event_photo':
            raise ValueError('Verified exact-event photo required for reel scenes')
    label = (credit.get('label_si') if image_kind in (
        'verified_institution_photo', 'verified_education_context_photo')
        and credit else None)
    facts = _story_facts(article, script)
    return [_slide(article, facts[i], i, image_path,
                   folder / f'scene_{i+1}.png', photo_label=label) for i in range(3)]


def render_bulletin(article, output_path='output/animated_news_bulletin.mp4'):
    """Three-scene vertical Sinhala voice bulletin; never copy TV footage."""
    import math
    from mutagen.mp3 import MP3
    from voice import create_voice
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    voice_path = output.with_suffix('.mp3')
    script = narration_for(article)
    if not create_voice(script, str(voice_path)):
        raise RuntimeError('Sinhala voice generation unavailable')
    duration = float(MP3(str(voice_path)).info.length)
    if not 3 <= duration <= 90:
        raise ValueError('Invalid narration length')

    scene_files = build_scene_images(article, script,
                                     output.parent / (output.stem + '_scenes'))
    frames = max(1, math.ceil(duration * 20))
    counts = [frames // 3] * 3
    for i in range(frames % 3):
        counts[i] += 1
    # Each distinct scene gets independent subtle zoom/pan; transitions are
    # clean cuts, never time-frozen blank backgrounds or unrelated imagery.
    filters = []
    args = ['ffmpeg', '-y', '-loglevel', 'error']
    for path in scene_files:
        args.extend(['-loop', '1', '-framerate', '20', '-i', str(path)])
    args.extend(['-i', str(voice_path)])
    for i, count in enumerate(counts):
        filters.append(
            f'[{i}:v]zoompan=z=\'min(zoom+0.00055,1.07)\':'
            f'x=\'iw/2-(iw/zoom/2)\':y=\'ih/2-(ih/zoom/2)\':'
            f'd={count}:s=720x1280:fps=20,trim=duration={count/20:.3f},'
            f'setpts=PTS-STARTPTS,format=yuv420p[v{i}]')
    filters.append(''.join(f'[v{i}]' for i in range(3)) +
                   'concat=n=3:v=1:a=0[v]')
    args.extend(['-filter_complex', ';'.join(filters), '-map', '[v]',
                 '-map', '3:a:0', '-t', str(duration), '-r', '20',
                 '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '26',
                 '-c:a', 'aac', '-b:a', '96k', '-pix_fmt', 'yuv420p',
                 '-movflags', '+faststart', '-shortest', str(output)])
    subprocess.run(args, check=True, timeout=240, capture_output=True)
    if not output.is_file() or output.stat().st_size < 20000:
        raise RuntimeError('Three-scene bulletin not created')
    return str(output)


def render_graphic_reel(article, output_path):
    """Generate a genuine moving branded news reel even if online Sinhala TTS fails.

    Uses only original slides or a vetted, correctly named institution photo;
    no unrelated live footage, borrowed audio or pretend voiceover.
    """
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    script = narration_for(article)
    slides = build_scene_images(article, script,
                                output.parent / (output.stem + '_graphic_scenes'))
    args = ['ffmpeg', '-y', '-loglevel', 'error']
    for image in slides:
        args.extend(['-loop', '1', '-framerate', '20', '-i', str(image)])
    args.extend(['-f', 'lavfi', '-i',
                 'anullsrc=channel_layout=stereo:sample_rate=44100'])
    filters = []
    for index in range(3):
        filters.append(
            f"[{index}:v]zoompan=z='min(zoom+0.0007,1.06)':"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"d=80:s=720x1280:fps=20,trim=duration=4,"
            f"setpts=PTS-STARTPTS,format=yuv420p[v{index}]")
    filters.append(''.join(f'[v{i}]' for i in range(3))
                   + 'concat=n=3:v=1:a=0[out]')
    args.extend(['-filter_complex', ';'.join(filters), '-map', '[out]',
                 '-map', '3:a:0', '-t', '12', '-r', '20', '-c:v', 'libx264',
                 '-preset', 'veryfast', '-crf', '26', '-c:a', 'aac',
                 '-b:a', '96k', '-pix_fmt', 'yuv420p', '-movflags',
                 '+faststart', '-shortest', str(output)])
    subprocess.run(args, check=True, timeout=180, capture_output=True)
    if not output.is_file() or output.stat().st_size < 20000:
        raise RuntimeError('Original graphic reel not created')
    return str(output)
