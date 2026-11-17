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


def script_runs(text):
    """Keep original Unicode content; switch glyph fonts without translating."""
    import re
    return re.findall(r'[\\u0D80-\\u0DFF]+|[^\\u0D80-\\u0DFF]+', str(text))


def mixed_width(draw, text, size, bold=False):
    sinhala = get_font(size, bold)
    latin = latin_font(size, bold)
    return sum(draw.textlength(run, font=sinhala if '\\u0d80' <= run[0] <= '\\u0dff' else latin)
               for run in script_runs(text))


def draw_mixed(draw, xy, text, size, fill='white', bold=False):
    """Draw Sinhala and Latin as separate shaped runs on a common baseline."""
    sinhala = get_font(size, bold)
    latin = latin_font(size, bold)
    x, y = xy
    for run in script_runs(text):
        font = sinhala if '\\u0d80' <= run[0] <= '\\u0dff' else latin
        draw.text((x, y), run, font=font, fill=fill, anchor='ls')
        x += draw.textlength(run, font=font)
    return x

def news_card(article):
    """Original typography card, never a substitute event photograph."""
    from pathlib import Path
    from PIL import Image, ImageDraw, ImageFont
    import re
    title = re.sub(r'\s*\((?:VIDEO|වීඩියෝ)\)', '', article['title_si'], flags=re.I)
    title = title.removeprefix('විස්තරාත්මක පුවත | ')
    canvas = Image.new('RGB', (1080, 1080), '#a90818')
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, 0, 1080, 150), fill='#670814')
    brand = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 58)
    draw.text((60, 45), 'SL NEWS 247', font=brand, fill='white')
    for size in range(72, 25, -2):
        font = get_font(size)
        lines, line = [], ''
        for word in title.split():
            trial = (line + ' ' + word).strip()
            if line and mixed_width(draw, trial, size) > 950:
                lines.append(line)
                line = word
            else:
                line = trial
        if line:
            lines.append(line)
        if len(lines) * size * 1.7 <= 540:
            break
    else:
        raise ValueError('Headline does not fit')
    y = 220
    for line in lines:
        draw_mixed(draw, (60, y + size), line, size, fill='white')
        y += int(size * 1.7)
    draw.rectangle((50, 820, 1030, 930), fill='#ffdd36')
    label = 'ආදර්ශ පළ කිරීමකි' if article.get('sample') else 'සම්පූර්ණ විස්තර පහතින්'
    draw_mixed(draw, (80, 890), label, 40, fill='#670814')
    Path('output').mkdir(exist_ok=True)
    path = 'output/card_' + re.sub('[^a-zA-Z0-9_-]', '', article['id']) + '.png'
    canvas.save(path)
    return path
