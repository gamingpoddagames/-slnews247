import os
import requests
from io import BytesIO

from PIL import (
    Image,
    ImageDraw,
    ImageFont,
    ImageFilter
)

from config import VIDEO_WIDTH, VIDEO_HEIGHT

CRIMSON = '#b92136'
YELLOW = '#ffe24a'

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}


# ==========================================
# Download Image
# ==========================================

def download_image(url, save_path):

    if not url:
        return False

    try:

        r = requests.get(
            url,
            headers=HEADERS,
            timeout=30
        )

        if r.status_code != 200:
            return False

        img = Image.open(
            BytesIO(r.content)
        ).convert("RGB")

        if img.width < 200 or img.height < 200:
            return False

        os.makedirs(
            os.path.dirname(save_path),
            exist_ok=True
        )

        img.save(
            save_path,
            quality=95
        )

        return True

    except Exception as e:

        print(e)

        return False


# ==========================================
# Resize Image
# ==========================================

def cover_resize(img, size):

    target_w, target_h = size

    img_w, img_h = img.size

    scale = max(
        target_w / img_w,
        target_h / img_h
    )

    new_w = int(img_w * scale)
    new_h = int(img_h * scale)

    img = img.resize(
        (new_w, new_h),
        Image.LANCZOS
    )

    left = (new_w - target_w) // 2
    top = (new_h - target_h) // 2

    return img.crop((
        left,
        top,
        left + target_w,
        top + target_h
    ))
  # ==========================================
# Dark Overlay
# ==========================================

def dark_overlay(img):

    overlay = Image.new(
        "RGBA",
        img.size,
        (0,0,0,0)
    )

    draw = ImageDraw.Draw(overlay)

    for y in range(VIDEO_HEIGHT):

        alpha = int(
            170 * (y / VIDEO_HEIGHT)
        )

        draw.line(

            [(0,y),(VIDEO_WIDTH,y)],

            fill=(0,0,0,alpha)

        )

    return Image.alpha_composite(

        img.convert("RGBA"),

        overlay

    ).convert("RGB")


# ==========================================
# Blur Background
# ==========================================

def create_background(image_path):

    img = Image.open(
        image_path
    ).convert("RGB")

    img = cover_resize(

        img,

        (VIDEO_WIDTH, VIDEO_HEIGHT)

    )

    img = img.filter(

        ImageFilter.GaussianBlur(18)

    )

    img = dark_overlay(img)

    return img
  # ==========================================
# Fallback Background
# ==========================================

def create_fallback(path):

    img = Image.new(

        "RGB",

        (VIDEO_WIDTH, VIDEO_HEIGHT),

        (12,25,60)

    )

    draw = ImageDraw.Draw(img)

    for y in range(VIDEO_HEIGHT):

        c = int(25 + y * 0.03)

        draw.line(

            [(0,y),(VIDEO_WIDTH,y)],

            fill=(10,c,80)

        )

    img.save(path)


# ==========================================
# Load Sinhala Font
# ==========================================

def get_font(size, bold=False):
    """Require a real Sinhala font; never silently draw missing-glyph boxes."""
    from pathlib import Path
    weight = 'Bold' if bold else 'Regular'
    candidates = [
        f'/usr/share/fonts/truetype/noto/NotoSansSinhala-{weight}.ttf',
        f'/usr/share/fonts/truetype/noto/NotoSerifSinhala-{weight}.ttf',
        f'/usr/local/share/fonts/NotoSansSinhala-{weight}.ttf',
        str(Path(__file__).resolve().parent / 'assets/sinhala_fonts/NotoSansSinhala-Variable.ttf'),
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            if not ImageFont.core.HAVE_RAQM:
                raise RuntimeError('Pillow requires libraqm for correct Sinhala shaping')
            font = ImageFont.truetype(candidate, size, layout_engine=ImageFont.Layout.RAQM)
            if candidate.endswith('-Variable.ttf'):
                # Google Fonts stores Weight before Width; never assume the
                # filename's [wdth,wght] order is the actual axis order.
                axes = font.get_variation_axes()
                values = [
                    max(axis['minimum'], min(axis['maximum'], 700 if bold else 400))
                    if axis['name'].decode('utf-8').lower() == 'weight'
                    else axis['default']
                    for axis in axes
                ]
                font.set_variation_by_axes(values)
            return font
    raise RuntimeError('Sinhala font unavailable: install fonts-noto-core')


def latin_font(size, bold=False):
    weight = 'Bold' if bold else ''
    path = '/usr/share/fonts/truetype/dejavu/DejaVuSans' + ('-' + weight if weight else '') + '.ttf'
    return ImageFont.truetype(path, size, layout_engine=ImageFont.Layout.RAQM)


def _sinhala_char(char):
    """Sinhala code points and Sinhala shaping joiners use the Sinhala font."""
    return ('\u0D80' <= char <= '\u0DFF') or char in ('\u200C', '\u200D')


def script_runs(text):
    """Keep full Unicode syllable clusters together and switch scripts safely."""
    import unicodedata
    text = unicodedata.normalize('NFC', str(text))
    if not text:
        return []
    runs = []
    current = text[0]
    current_is_sinhala = _sinhala_char(text[0])
    for char in text[1:]:
        is_sinhala = _sinhala_char(char)
        if is_sinhala == current_is_sinhala:
            current += char
        else:
            runs.append(current)
            current = char
            current_is_sinhala = is_sinhala
    runs.append(current)
    return runs


def mixed_width(draw, text, size, bold=False):
    sinhala = get_font(size, bold)
    latin = latin_font(size, bold)
    return sum(
        draw.textlength(run, font=sinhala if _sinhala_char(run[0]) else latin)
        for run in script_runs(text)
    )


def draw_mixed(draw, xy, text, size, fill='white', bold=False):
    """Render Sinhala with Noto + RAQM, English with DejaVu, never tofu boxes."""
    sinhala = get_font(size, bold)
    latin = latin_font(size, bold)
    x, y = xy
    for run in script_runs(text):
        font = sinhala if _sinhala_char(run[0]) else latin
        draw.text((x, y), run, font=font, fill=fill, anchor='ls')
        x += draw.textlength(run, font=font)
    return x


def fit_headline(draw, title, width=950, max_height=550, start_size=72, min_size=20, bold=False):
    """Size Sinhala/English text using actual glyph measurements, never clipping."""
    if not title or not title.strip():
        raise ValueError('A news card requires a title')
    for size in range(start_size, min_size - 1, -2):
        lines, current = [], ''
        for word in title.split():
            trial = (current + ' ' + word).strip()
            if mixed_width(draw, trial, size, bold=bold) <= width:
                current = trial
            else:
                if current:
                    lines.append(current)
                current = word
                # Long unbreakable words must not escape the card boundary.
                if mixed_width(draw, current, size, bold=bold) > width:
                    break
        else:
            if current:
                lines.append(current)
            step = int(size * 1.48)
            if (lines and len(lines) * step <= max_height
                    and all(mixed_width(draw, line, size, bold=bold) <= width for line in lines)):
                return size, lines, step
    raise ValueError('Headline too long for readable card; keep full title in post caption')


def _fitted_lines(draw, text, width, height, sizes):
    # Keep a short introductory clause together rather than letting its last
    # word spill into the main fact (for example, a calendar heading).
    prefix, colon, remainder = text.partition(':')
    if colon and remainder.strip() and len(prefix) <= 60:
        prefix += ':'
        for size in sizes:
            step = int(size * 1.48)
            if mixed_width(draw, prefix, size, bold=True) > width:
                continue
            try:
                _, tail, _ = fit_headline(draw, remainder.strip(), width,
                                          height-step, size, size, bold=True)
                return size, [prefix] + tail, step
            except ValueError:
                continue
    for size in sizes:
        try:
            fs, lines, step = fit_headline(draw, text, width, height, size, size, bold=True)
            return fs, lines, step
        except ValueError:
            continue
    raise ValueError('Headline cannot fit the poster safely')


def broadcast_background(size, frame_box, radius):
    """Shared warm/blue surround and white rounded frame for posts and reels."""
    width, height = size
    canvas = Image.new('RGB', size)
    gradient = ImageDraw.Draw(canvas)
    for y in range(height):
        if y < height // 2:
            t = y / (height // 2)
            color = (round(255 - 52*t), round(142 - 117*t), round(23 + 28*t))
        else:
            t = (y - height // 2) / (height - height // 2)
            color = (round(17 - 7*t), round(101 - 60*t), round(184 - 79*t))
        gradient.line((0, y, width, y), fill=color)
    glow = Image.new('RGBA', size)
    ImageDraw.Draw(glow).ellipse(
        (width*.03, -height*.13, width*.77, height*.13), fill=(255, 240, 191, 90))
    canvas = Image.alpha_composite(
        canvas.convert('RGBA'), glow.filter(ImageFilter.GaussianBlur(65))).convert('RGB')
    ImageDraw.Draw(canvas).rounded_rectangle(frame_box, radius=radius, fill='white')
    return canvas


def crimson_panel(size):
    """Logo-matched crimson with a restrained darker red lower edge."""
    width, height = size
    panel = Image.new('RGB', size, CRIMSON)
    draw = ImageDraw.Draw(panel)
    for y in range(height):
        t = y / max(1, height - 1)
        draw.line((0, y, width, y), fill=(round(185 - 28*t),
                                       round(33 - 10*t), round(54 - 8*t)))
    return panel


def news_card(article, image_path=None, illustrative=False, photo_label=None, *, graphic_fallback=False):
    """Photo-first crimson poster with bold yellow/white Sinhala headlines.

    Callers verify the asset's story match and reuse rights before rendering.
    Explicit graphic fallback uses an original topic illustration.
    Media descriptions stay in internal records, not over the photograph.
    """
    from pathlib import Path
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from PIL import ImageOps
    import re

    if not image_path and not graphic_fallback:
        raise ValueError('A verified real photo or event-video frame is required')
    title = re.sub(r'\s*\((?:VIDEO|වීඩියෝ)\)', '', article['title_si'], flags=re.I)
    title = title.removeprefix('විස්තරාත්මක පුවත | ').strip()
    width, height = 1080, 1350
    canvas = broadcast_background((width, height), (32, 56, 1048, 1295), 88)
    # Build the centre separately, then clip photo and headline to one rounded mask.
    panel = crimson_panel((988, 1212))
    if image_path:
        with Image.open(image_path) as src:
            photo = ImageOps.fit(ImageOps.exif_transpose(src).convert('RGB'), (988, 752),
                                 method=Image.Resampling.LANCZOS)
        panel.paste(photo, (0, 0))
    else:
        from story_visual import draw_story_hero
        draw_story_hero(panel, article, (0, 0, 987, 751))
    panel.paste(crimson_panel((988, 460)), (0, 752))
    mask = Image.new('L', panel.size)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, 987, 1211), radius=76, fill=255)
    canvas.paste(panel, (46, 70), mask)

    # Top date and original brand only (no third-party logo/watermarks).
    draw = ImageDraw.Draw(canvas)
    date = datetime.fromtimestamp(
        article.get('published', __import__('time').time()), ZoneInfo('Asia/Colombo')
    ).strftime('%d.%m.%Y')
    latin = latin_font(35, bold=True)
    draw.rounded_rectangle((75, 89, 326, 147), radius=14, fill='#fff8ed', outline='white', width=2)
    draw.text((95, 100), date, font=latin, fill='#18324e')
    draw.rounded_rectangle((722, 22, 1027, 132), radius=22, fill='#b92136', outline='white', width=3)
    draw.rounded_rectangle((730, 30, 1019, 64), radius=15, fill='#d84c45')
    draw.text((748, 35), 'SL NEWS', font=latin_font(41, bold=True), fill='white')
    draw.text((884, 82), '24/7', font=latin_font(28, bold=True), fill='#ffe094')

    draw.rectangle((77, 839, 173, 845), fill=YELLOW)
    draw.line((188, 842, 1003, 842), fill='#d88b54', width=2)
    draw.line((88, 1222, 992, 1222), fill='#d88b54', width=1)
    draw.text((88, 1240), 'SL NEWS 24/7', font=latin_font(20, bold=True), fill='white')
    draw_mixed(draw, (727, 1260), 'පැය විසිහතර පුරාම', 20, fill=YELLOW, bold=True)
    # Fit the complete headline as one block; never split a phrase arbitrarily.
    group = _fitted_lines(draw, title, 888, 310, range(72, 31, -2))
    size, lines, step = group
    baseline = 872 + size + max(0, (310 - len(lines) * step) // 2)
    for index, line in enumerate(lines):
        x = 540 - mixed_width(draw, line, size, bold=True) / 2
        draw_mixed(draw, (x, baseline), line, size,
                   fill=YELLOW if index == 0 else 'white', bold=True)
        baseline += step
    # Preserve the clean lower margin required by the production layout.

    Path('output').mkdir(exist_ok=True)
    safe_id = re.sub('[^a-zA-Z0-9_-]', '', str(article.get('id', 'news'))) or 'news'
    path = 'output/card_' + safe_id + '.png'
    canvas.save(path, optimize=True)
    return path

