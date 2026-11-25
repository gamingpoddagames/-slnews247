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


def news_card(article, image_path=None, illustrative=False, photo_label=None):
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
    # Glass broadcast frame: restrained cyan highlights over midnight blue.
    for y in range(height):
        t = y / height
        gradient.line((0, y, width, y),
                      fill=(int(7 + 7*t), int(18 + 13*t), int(43 + 24*t)))
    glow = Image.new('RGBA', canvas.size)
    gd = ImageDraw.Draw(glow)
    gd.ellipse((-260, -240, 720, 650), fill=(0, 173, 255, 100))
    gd.ellipse((730, 800, 1400, 1510), fill=(110, 48, 255, 95))
    canvas = Image.alpha_composite(canvas.convert('RGBA'),
                                 glow.filter(ImageFilter.GaussianBlur(100))).convert('RGB')
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((30, 55, 1050, 1297), radius=42,
                           fill='#101e36', outline='#63d9ff', width=2)
    draw.rounded_rectangle((40, 65, 1040, 1287), radius=34,
                           outline='#314e70', width=1)
    photo_rect = (46, 70, 1034, 822)
    if image_path:
        with Image.open(image_path) as src:
            photo = __import__('PIL.ImageOps', fromlist=['fit']).fit(
                src.convert('RGB'), (photo_rect[2]-photo_rect[0], photo_rect[3]-photo_rect[1]),
                method=Image.Resampling.LANCZOS)
        canvas.paste(photo, (photo_rect[0], photo_rect[1]))
    else:
        # An original, incident-specific news infographic—not an empty gradient
        # or an unrelated illustration—uses factual figures and topic artwork.
        from story_visual import draw_story_hero
        draw_story_hero(canvas, article, photo_rect)

    # Top date and original brand only (no third-party logo/watermarks).
    draw = ImageDraw.Draw(canvas)
    date = datetime.fromtimestamp(
        article.get('published', __import__('time').time()), ZoneInfo('Asia/Colombo')
    ).strftime('%d.%m.%Y')
    latin = latin_font(35, bold=True)
    draw.rounded_rectangle((75, 89, 326, 147), radius=14, fill='#1a2031')
    draw.text((95, 100), date, font=latin, fill='white')
    draw.rounded_rectangle((722, 22, 1027, 132), radius=22, fill='#0b426e', outline='#83e5ff', width=2)
    draw.text((750, 36), 'SL NEWS', font=latin_font(41, bold=True), fill='white')
    draw.text((891, 80), '24/7', font=latin_font(27, bold=True), fill='#91edff')

    if image_path and photo_label:
        # Identify archival institution photography without implying that
        # the picture captures the specific announcement or meeting.
        draw.rounded_rectangle((100, 704, 950, 777), radius=16, fill='#15243f')
        draw_mixed(draw, (120, 754), str(photo_label)[:46], 27,
                   fill='#ffffff', bold=True)
    elif image_path and illustrative:
        draw.rounded_rectangle((110, 708, 720, 777), radius=16, fill='#15243f')
        draw_mixed(draw, (132, 758), 'සංකේතාත්මක රූපයක්', 33,
                   fill='#ffffff', bold=True)

    # Fade/cover lower photo margin with a charcoal headline field.
    draw.rectangle((46, 793, 1034, 1282), fill='#101e36')
    draw.line((76, 811, 1004, 811), fill='#67ddff', width=3)
    draw.line((76, 816, 1004, 816), fill='#244f72', width=1)
    draw.rounded_rectangle((76, 1230, 1004, 1268), radius=12, fill='#18304c')
    draw.text((94, 1237), 'SL NEWS 24/7', font=latin_font(20, bold=True), fill='#9cecff')
    draw_mixed(draw, (710, 1256), 'පැය විසිහතර පුරාම', 20, fill='#d5e9f8')
    # Fit the complete headline as one block; never split a phrase arbitrarily.
    group = _fitted_lines(draw, title, 886, 370, range(68, 23, -2))
    size, lines, step = group
    baseline = 842 + size + max(0, (370 - len(lines) * step) // 2)
    for index, line in enumerate(lines):
        x = 540 - mixed_width(draw, line, size, bold=True) / 2
        draw_mixed(draw, (x, baseline), line, size,
                   fill='#8beaff' if index == 0 else '#ffffff', bold=True)
        baseline += step
    # Preserve the clean lower margin required by the production layout.

    Path('output').mkdir(exist_ok=True)
    safe_id = re.sub('[^a-zA-Z0-9_-]', '', str(article.get('id', 'news'))) or 'news'
    path = 'output/card_' + safe_id + '.png'
    canvas.save(path, optimize=True)
    return path
