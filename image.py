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
        str(Path(__file__).resolve().parent / 'assets/sinhala_fonts/NotoSansSinhala-Variable.ttf'),
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            if not ImageFont.core.HAVE_RAQM:
                raise RuntimeError('Pillow requires libraqm for correct Sinhala shaping')
            font = ImageFont.truetype(candidate, size, layout_engine=ImageFont.Layout.RAQM)
            if bold and candidate.endswith('-Variable.ttf'):
                try:
                    font.set_variation_by_axes([100, 700])  # width=100, weight=700
                except (OSError, ValueError):
                    pass
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


def _fitted_lines(draw, text, width, height, sizes):
    for size in sizes:
        try:
            fs, lines, step = fit_headline(draw, text, width, height, size, size)
            return fs, lines, step
        except ValueError:
            continue
    raise ValueError('Headline cannot fit the poster safely')


def news_card(article, image_path=None, illustrative=False):
    """Original broadcast-style 1080x1350 news poster.

    The photo is allowed only after media.choose_photo has verified the
    matching story and permission. No invented depiction or publisher logo.
    """
    from pathlib import Path
    from datetime import datetime
    from zoneinfo import ZoneInfo
    import re

    title = re.sub(r'\s*\((?:VIDEO|වීඩියෝ)\)', '', article['title_si'], flags=re.I)
    title = title.removeprefix('විස්තරාත්මක පුවත | ').strip()
    width, height = 1080, 1350
    canvas = Image.new('RGB', (width, height))
    gradient = ImageDraw.Draw(canvas)
    # Upper frame: existing warm news colors; lower frame: deep blue.
    # Keep the transition at the poster's midpoint for a balanced two-tone border.
    for y in range(height):
        if y < height // 2:
            weight = y / (height // 2)
            color = (round(255 - 52 * weight),
                     round(142 - 117 * weight),
                     round(23 + 28 * weight))
        else:
            weight = (y - height // 2) / (height - height // 2)
            color = (round(17 - 7 * weight),
                     round(101 - 60 * weight),
                     round(184 - 79 * weight))
        gradient.line((0, y, width, y), fill=color)

    # Inner panel has a thick rounded white frame and dark lower portion.
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((32, 56, 1048, 1295), radius=88, fill='white')
    draw.rounded_rectangle((44, 68, 1036, 1283), radius=76, fill='#202124')
    photo_rect = (46, 70, 1034, 822)
    if image_path:
        with Image.open(image_path) as src:
            photo = __import__('PIL.ImageOps', fromlist=['fit']).fit(
                src.convert('RGB'), (photo_rect[2]-photo_rect[0], photo_rect[3]-photo_rect[1]),
                method=Image.Resampling.LANCZOS)
        canvas.paste(photo, (photo_rect[0], photo_rect[1]))
    else:
        # Approved no-photo treatment: one uninterrupted dark-blue, softly
        # shaded news field. Never show boxes, icons, crossed lines or labels.
        # Rendering at quarter resolution then Lanczos-scaling makes a soft
        # radial glow without expensive per-pixel work on GitHub Actions.
        from math import exp
        pw = photo_rect[2] - photo_rect[0]
        ph = photo_rect[3] - photo_rect[1]
        sample_w, sample_h = 247, 188
        shade = Image.new('RGB', (sample_w, sample_h))
        pixels = shade.load()
        for sy in range(sample_h):
            ny = sy / max(1, sample_h - 1)
            for sx in range(sample_w):
                nx = sx / max(1, sample_w - 1)
                # Deep navy at the perimeter; gentle royal-blue glow in center.
                r2 = ((nx - 0.48) / 0.53) ** 2 + ((ny - 0.47) / 0.68) ** 2
                glow = exp(-2.3 * r2)
                pixels[sx, sy] = (
                    round(3 + 9 * glow),
                    round(13 + 51 * glow),
                    round(57 + 101 * glow),
                )
        shade = shade.resize((pw, ph), Image.Resampling.LANCZOS)
        canvas.paste(shade, (photo_rect[0], photo_rect[1]))

    # Top date and original brand only (no third-party logo/watermarks).
    draw = ImageDraw.Draw(canvas)
    date = datetime.fromtimestamp(
        article.get('published', __import__('time').time()), ZoneInfo('Asia/Colombo')
    ).strftime('%d.%m.%Y')
    latin = latin_font(35, bold=True)
    draw.rounded_rectangle((75, 89, 326, 147), radius=14, fill='#1a2031')
    draw.text((95, 100), date, font=latin, fill='white')
    draw.rounded_rectangle((722, 22, 1027, 132), radius=22, fill='#a6081b', outline='white', width=5)
    draw.text((750, 36), 'SL NEWS', font=latin_font(41, bold=True), fill='white')
    draw.text((891, 80), '24/7', font=latin_font(27, bold=True), fill='#ffdc37')

    if image_path and illustrative:
        # Explicitly distinguish a contextual archive photo from event footage.
        draw.rounded_rectangle((110, 708, 720, 777), radius=16, fill='#15243f')
        draw_mixed(draw, (132, 758), 'සංකේතාත්මක ඡායාරූපයක්', 33,
                   fill='#ffffff', bold=True)

    # Fade/cover lower photo margin with a charcoal headline field.
    draw.rectangle((46, 793, 1034, 1282), fill='#202124')
    words = title.split()
    if not words:
        raise ValueError('Title missing')
    split = max(1, (len(words) + 1)//2)
    yellow = ' '.join(words[:split])
    white = ' '.join(words[split:])

    # Keep full source headline, split purely for layout. Avoid word clipping.
    upper = _fitted_lines(draw, yellow, 886, 170, range(58, 23, -2))
    lower = _fitted_lines(draw, white, 886, 238, range(68, 23, -2)) if white else None
    def center_lines(group, first_baseline, color):
        if group is None:
            return
        size, lines, step = group
        for line in lines:
            x = 540 - mixed_width(draw, line, size, bold=True)/2
            draw_mixed(draw, (x, first_baseline), line, size, fill=color, bold=True)
            first_baseline += step
    center_lines(upper, 880, '#ffdd32')
    if lower:
        center_lines(lower, 1068, 'white')
    # Quote-shaped original accents, outside the headline text region.
    draw.text((72, 1128), '“', font=latin_font(74, bold=True), fill='#fb5722')
    draw.text((953, 1190), '”', font=latin_font(74, bold=True), fill='#fb5722')

    Path('output').mkdir(exist_ok=True)
    safe_id = re.sub('[^a-zA-Z0-9_-]', '', str(article.get('id', 'news'))) or 'news'
    path = 'output/card_' + safe_id + '.png'
    canvas.save(path, optimize=True)
    return path
