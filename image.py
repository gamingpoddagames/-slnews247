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

    fonts = [

        "/usr/share/fonts/truetype/noto/NotoSansSinhala-Regular.ttf",

        "/usr/share/fonts/truetype/noto/NotoSansSinhala-Bold.ttf",

        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

    ]

    for f in fonts:

        try:

            return ImageFont.truetype(

                f,

                size

            )

        except:

            pass

    return ImageFont.load_default()

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
            if line and draw.textlength(trial, font=font) > 950:
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
        draw.text((60, y), line, font=font, fill='white')
        y += int(size * 1.7)
    draw.rectangle((50, 820, 1030, 930), fill='#ffdd36')
    label = 'ආදර්ශ පළ කිරීමකි' if article.get('sample') else 'සම්පූර්ණ විස්තර පහතින්'
    draw.text((80, 845), label, font=get_font(40), fill='#670814')
    Path('output').mkdir(exist_ok=True)
    path = 'output/card_' + re.sub('[^a-zA-Z0-9_-]', '', article['id']) + '.png'
    canvas.save(path)
    return path
