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
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            if not ImageFont.core.HAVE_RAQM:
                raise RuntimeError('Pillow requires libraqm for correct Sinhala shaping')
            return ImageFont.truetype(candidate, size, layout_engine=ImageFont.Layout.RAQM)
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


def fit_headline(draw, title, width=950, max_height=550, start_size=72, min_size=20):
    """Size Sinhala/English text using actual glyph measurements, never clipping."""
    if not title or not title.strip():
        raise ValueError('A news card requires a title')
    for size in range(start_size, min_size - 1, -2):
        lines, current = [], ''
        for word in title.split():
            trial = (current + ' ' + word).strip()
            if mixed_width(draw, trial, size) <= width:
                current = trial
            else:
                if current:
                    lines.append(current)
                current = word
                # Long unbreakable words must not escape the card boundary.
                if mixed_width(draw, current, size) > width:
                    break
        else:
            if current:
                lines.append(current)
            step = int(size * 1.48)
            if (lines and len(lines) * step <= max_height
                    and all(mixed_width(draw, line, size) <= width for line in lines)):
                return size, lines, step
    raise ValueError('Headline too long for readable card; keep full title in post caption')


def news_card(article):
    """Original 1080x1080 post card with fully measured, contained headline."""
    from pathlib import Path
    import re
    title = re.sub(r'\s*\((?:VIDEO|වීඩියෝ)\)', '', article['title_si'], flags=re.I)
    title = title.removeprefix('විස්තරාත්මක පුවත | ')
    canvas = Image.new('RGB', (1080, 1080), '#a90818')
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, 0, 1080, 150), fill='#670814')
    brand = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 54)
    draw.text((60, 49), 'SL NEWS 24/7', font=brand, fill='white')
    size, lines, step = fit_headline(draw, title)
    y = 205
    for line in lines:
        draw_mixed(draw, (60, y + size), line, size, fill='white')
        y += step
    draw.rectangle((50, 830, 1030, 935), fill='#ffdd36')
    label = 'ආදර්ශ පළ කිරීමකි' if article.get('sample') else 'සම්පූර්ණ විස්තර පහතින්'
    label_size, label_lines, _ = fit_headline(
        draw, label, width=910, max_height=75, start_size=40, min_size=22)
    if len(label_lines) != 1:
        raise ValueError('Footer label does not fit on one line')
    draw_mixed(draw, (80, 868 + label_size), label_lines[0],
               label_size, fill='#670814')
    Path('output').mkdir(exist_ok=True)
    path = 'output/card_' + re.sub('[^a-zA-Z0-9_-]', '', article['id']) + '.png'
    canvas.save(path)
    return path
