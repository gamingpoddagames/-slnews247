"""Render one Sinhala news card once, then encode using FFmpeg."""
import subprocess
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
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


def create_card(title, summary, path):
    card = Image.new('RGB', (1080, 1920), '#081225')
    draw = ImageDraw.Draw(card)
    draw.rectangle((0, 0, 1080, 20), fill='#ef4056')
    draw.text((75, 120), 'WORLD NEWS', font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 62), fill='white')
    draw.text((75, 215), 'සිංහල පුවත්', font=get_font(48), fill='#52dbc3')
    draw.rounded_rectangle((55, 370, 1025, 1010), radius=32, fill='#142642')
    fit(draw, title, (90, 420, 900, 540), 64, 30)
    fit(draw, summary, (90, 1080, 880, 560), 40, 24)
    draw.line((90, 1720, 990, 1720), fill='#52dbc3', width=3)
    draw.text((90, 1760), 'Source and article link in caption', font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 30), fill='#a9bacf')
    draw.text((90, 1820), 'Follow for more world news', font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 30), fill='#a9bacf')
    card.save(path)


def create_video(image_path, audio_path, title, summary, output_path):
    card = str(Path(output_path).with_suffix('.png'))
    create_card(title, summary, card)
    subprocess.run(['ffmpeg', '-y', '-loop', '1', '-framerate', '25', '-i', card,
                    '-i', audio_path, '-c:v', 'libx264', '-tune', 'stillimage',
                    '-preset', 'veryfast', '-crf', '25', '-c:a', 'aac', '-b:a', '128k',
                    '-pix_fmt', 'yuv420p', '-shortest', '-movflags', '+faststart', output_path],
                   check=True, timeout=240, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return True
