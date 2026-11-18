"""Render one Sinhala news card once, then encode using FFmpeg."""
import subprocess
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps
from image import get_font, mixed_width, draw_mixed


def wrap(draw, text, font, width):
    lines, current = [], ''
    for word in text.split():
        trial = (current + ' ' + word).strip()
        if current and mixed_width(draw, trial, font.size) > width:
            lines.append(current)
            current = word
        else:
            current = trial
    if current:
        lines.append(current)
    return lines


def fit(draw, text, box, start, minimum=20):
    x, y, width, height = box
    for size in range(start, minimum - 1, -2):
        font = get_font(size)
        lines = wrap(draw, text, font, width)
        step = int(size * 1.65)
        if lines and len(lines) * step <= height and all(mixed_width(draw, line, size) <= width for line in lines):
            for line in lines:
                draw_mixed(draw, (x, y + size), line, size, fill='white')
                y += step
            return
    raise ValueError('News text does not fit card; refusing clipped output')


def create_card(title, summary, path, image_path=None, height=1920, contextual=True):
    card = Image.new('RGB', (1080, height), '#081225')
    draw = ImageDraw.Draw(card)
    draw.rectangle((0, 0, 1080, 16), fill='#ef4056')
    english = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
    draw.text((65, 65), 'SL NEWS 24/7', font=ImageFont.truetype(english, 52), fill='white')
    if height == 1920:
        draw_mixed(draw, (65, 196), 'සිංහල පුවත්', 38, fill='#52dbc3')
        photo_box = (45, 270, 1035, 1030)
        title_box, summary_box = (65, 1110, 950, 350), (65, 1500, 950, 210)
        footer_y = 1780
    else:
        photo_box = (35, 175, 1045, 785)
        title_box, summary_box = (60, 830, 960, 300), (60, 1150, 960, 0)
        footer_y = 1240
    if image_path and Path(image_path).exists():
        x0, y0, x1, y1 = photo_box
        with Image.open(image_path) as image:
            photo = ImageOps.fit(image.convert('RGB'), (x1-x0, y1-y0), method=Image.Resampling.LANCZOS)
        card.paste(photo, (x0, y0))
        draw = ImageDraw.Draw(card)
        if contextual:
            draw.rectangle((x0, y1-64, x1, y1), fill='#142642')
            draw_mixed(draw, (x0+20, y1-24), 'පසුබිම් ඡායාරූපයකි', 27, fill='#d8e4ed')
    fit(draw, title, title_box, 54, 24)
    if summary_box[3] and summary:
        fit(draw, summary, summary_box, 30, 22)
    draw.line((65, footer_y-15, 1015, footer_y-15), fill='#52dbc3', width=3)
    draw.text((65, footer_y+12), 'Follow for Sri Lanka news', font=ImageFont.truetype(english, 29), fill='#a9bacf')
    card.save(path)


def create_video(image_path, audio_path, title, summary, output_path, contextual=True):
    card = str(Path(output_path).with_suffix('.png'))
    create_card(title, summary, card, image_path, contextual=contextual)
    subprocess.run(['ffmpeg', '-y', '-loop', '1', '-framerate', '25', '-i', card,
                    '-i', audio_path, '-c:v', 'libx264', '-tune', 'stillimage',
                    '-preset', 'veryfast', '-crf', '25', '-c:a', 'aac', '-b:a', '128k',
                    '-pix_fmt', 'yuv420p', '-shortest', '-movflags', '+faststart', output_path],
                   check=True, timeout=240, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return True


def probe_footage(path):
    import json
    result = subprocess.run(['ffprobe', '-v', 'error', '-show_streams', '-show_format',
                             '-of', 'json', path], capture_output=True, text=True, check=True, timeout=20)
    info = json.loads(result.stdout)
    video = next((s for s in info.get('streams', []) if s.get('codec_type') == 'video'), None)
    duration = float(info.get('format', {}).get('duration', 0))
    if not video or duration < 1 or video.get('disposition', {}).get('attached_pic'):
        raise ValueError('File is not a usable video clip')
    frames = video.get('nb_frames')
    # Many valid H.264 streams report N/A rather than an integer frame count.
    # Reject explicitly single-frame files, but accept unknown counts only when
    # their encoded frame rate and duration indicate moving footage is possible.
    if frames not in (None, '', 'N/A'):
        try:
            if int(frames) < 2:
                raise ValueError('A still photo is not event footage')
        except (TypeError, ValueError) as exc:
            if str(exc) == 'A still photo is not event footage':
                raise
            raise ValueError('Invalid frame count') from exc
    else:
        rate = video.get('avg_frame_rate') or video.get('r_frame_rate') or '0/1'
        try:
            from fractions import Fraction
            fps = float(Fraction(rate))
        except (ValueError, ZeroDivisionError):
            fps = 0
        if fps <= 0 or fps * duration < 2:
            raise ValueError('Footage does not contain enough video frames')
    return {'duration': duration, 'has_audio': any(s.get('codec_type') == 'audio' for s in info['streams'])}


def trim_reviewed_ad_segments(clip_path, output_path, ad_segments, reviewed=False):
    """Remove human-reviewed ad intervals from an authorized source video.

    This never detects ads heuristically or removes source watermarks. Retained
    footage must belong to the same verified event. The original file is intact.
    """
    if not reviewed:
        raise ValueError('Ad edits must be reviewed before processing')
    info = probe_footage(clip_path)
    duration = info['duration']
    if not 0 < duration <= 7200:
        raise ValueError('Unexpected footage duration')
    if not isinstance(ad_segments, list) or not ad_segments or len(ad_segments) > 12:
        raise ValueError('Expected 1-12 reviewed ad intervals')
    intervals = []
    for segment in ad_segments:
        if not isinstance(segment, (list, tuple)) or len(segment) != 2:
            raise ValueError('Ad intervals must be [start_seconds, end_seconds]')
        start, end = segment
        if (not isinstance(start, (float, int)) or isinstance(start, bool)
                or not isinstance(end, (float, int)) or isinstance(end, bool)
                or not 0 <= start < end <= duration):
            raise ValueError('Ad interval outside footage')
        intervals.append((float(start), float(end)))
    intervals.sort()
    if any(intervals[i][1] > intervals[i + 1][0] for i in range(len(intervals) - 1)):
        raise ValueError('Overlapping ad intervals')
    retain = []
    cursor = 0.0
    for start, end in intervals:
        if start - cursor >= 0.15:
            retain.append((cursor, start))
        cursor = end
    if duration - cursor >= 0.15:
        retain.append((cursor, duration))
    if not retain:
        raise ValueError('Nothing remains after reviewed ad cuts')
    filters = []
    segments = []
    for i, (start, end) in enumerate(retain):
        filters.append(f'[0:v]trim=start={start:.3f}:end={end:.3f},setpts=PTS-STARTPTS[v{i}]')
        segments.append(f'[v{i}]')
    filters.append(''.join(segments) + f'concat=n={len(segments)}:v=1:a=0[out]')
    subprocess.run(
        ['ffmpeg', '-y', '-i', str(clip_path), '-filter_complex', ';'.join(filters),
         '-map', '[out]', '-an', '-c:v', 'libx264', '-preset', 'veryfast',
         '-crf', '23', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(output_path)],
        check=True, timeout=240, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return str(output_path)


def create_footage_video(clip_path, title, summary, output_path, audio_path=None):
    """Use reviewed footage and a separate Sinhala narration; never source audio."""
    info = probe_footage(clip_path)
    if not audio_path:
        raise ValueError('Sinhala narration is required')
    import json
    narration = subprocess.run(
        ['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(audio_path)],
        capture_output=True, text=True, check=True, timeout=20)
    audio_info = json.loads(narration.stdout)
    duration = float(audio_info.get('format', {}).get('duration', 0))
    if (not any(s.get('codec_type') == 'audio' for s in audio_info.get('streams', []))
            or not 0 < duration <= min(info['duration'], 90)):
        raise ValueError('Complete narration must fit available footage and 90 seconds')
    card = str(Path(output_path).with_suffix('.png'))
    create_card(title, summary, card, contextual=False)
    filters = ('[0:v]scale=990:760:force_original_aspect_ratio=decrease,'
               'pad=990:760:(ow-iw)/2:(oh-ih)/2:black,setsar=1[footage];'
               '[1:v][footage]overlay=45:270:shortest=1,format=yuv420p[out]')
    args = ['ffmpeg', '-y', '-i', clip_path, '-loop', '1', '-i', card,
            '-i', str(audio_path), '-filter_complex', filters, '-map', '[out]', '-map', '2:a:0',
            '-t', str(duration), '-r', '25', '-c:v', 'libx264',
            '-preset', 'veryfast', '-crf', '24', '-c:a', 'aac', '-b:a', '128k',
            '-movflags', '+faststart', '-shortest', output_path]
    subprocess.run(args, check=True, timeout=240, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return True
