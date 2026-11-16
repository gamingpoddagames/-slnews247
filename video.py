"""Render one Sinhala news card once, then encode using FFmpeg."""
import subprocess
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps
from image import get_font


def wrap(draw, text, font, width):
    lines, current = [], ''
    for word in text.split():
        trial = (current + ' ' + word).strip()
        if current and draw.textlength(trial, font=font) > width:
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
        if len(lines) * step <= height and all(draw.textlength(line, font=font) <= width for line in lines):
            for line in lines:
                draw.text((x, y), line, font=font, fill='white')
                y += step
            return
    raise ValueError('News text does not fit card; refusing clipped output')


def create_card(title, summary, path, image_path=None, height=1920, contextual=True):
    card = Image.new('RGB', (1080, height), '#081225')
    draw = ImageDraw.Draw(card)
    draw.rectangle((0, 0, 1080, 16), fill='#ef4056')
    english = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
    draw.text((65, 65), 'SL NEWS 247', font=ImageFont.truetype(english, 52), fill='white')
    if height == 1920:
        draw.text((65, 155), 'සිංහල පුවත්', font=get_font(38), fill='#52dbc3')
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
            draw.text((x0+20, y1-55), 'පසුබිම් ඡායාරූපයකි', font=get_font(27), fill='#d8e4ed')
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
