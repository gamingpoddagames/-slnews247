"""Create an original news-graphics demo with Sinhala narration using Google TTS."""
from pathlib import Path
import subprocess
from PIL import Image, ImageDraw, ImageFont
from gtts import gTTS

ROOT = Path("output/voice_demo")
ROOT.mkdir(parents=True, exist_ok=True)
SINHALA = "/usr/share/fonts/truetype/noto/NotoSansSinhala-Regular.ttf"
BOLD = "/usr/share/fonts/truetype/noto/NotoSansSinhala-Bold.ttf"
LATIN = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
STORY = [
    ("WEATHER UPDATE", "ශ්‍රී ලංකාවේ වායු ගුණාත්මකභාවය ගැන අවධානය",
     "ශ්‍රී ලංකාවේ වායු ගුණාත්මකභාවය පිළිබඳ වාර්තා සහ නවතම කාලගුණ නිවේදන ගැන අවධානයෙන් සිටින්න."),
    ("COLOMBO", "කොළඹ ඇතුළු ප්‍රදේශවල මීදුම් වැනි තත්ත්වයක්",
     "කොළඹ ඇතුළු ප්‍රදේශවල මීදුම් වැනි තත්ත්වයන් ගැන වාර්තා පළ වී තිබෙනවා."),
    ("SL NEWS 247", "නිල කාලගුණ දැනුම්දීම් අනුගමනය කරන්න",
     "නිල කාලගුණ දැනුම්දීම් අනුගමනය කරන්න. අලුත්ම පුවත් සඳහා එස් එල් නිව්ස් ට්වෙන්ටි ෆෝ සෙවන් සමඟ රැඳී සිටින්න."),
]

def run(command):
    subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

def wrap(draw, text, font, width):
    result = []
    line = ""
    for word in text.split():
        trial = (line + " " + word).strip()
        if line and draw.textlength(trial, font=font) > width:
            result.append(line)
            line = word
        else:
            line = trial
    if line:
        result.append(line)
    return result

def slide(i, tag, headline):
    im = Image.new("RGB", (720, 1280), "#0B1627")
    d = ImageDraw.Draw(im)
    for y in range(0, 1280, 4):
        d.line((0, y, 720, y), fill=(12, 22 + int(18 * y / 1280), 39 + int(20 * y / 1280)), width=4)
    d.rectangle((0, 0, 720, 18), fill="#FFD23F")
    d.rounded_rectangle((35, 52, 685, 150), 18, fill="#192E47")
    d.text((55, 77), "SL NEWS 247", font=ImageFont.truetype(LATIN, 49), fill="white")
    d.rounded_rectangle((40, 225, 680, 315), 22, fill="#B90E25")
    d.text((62, 248), tag, font=ImageFont.truetype(LATIN, 36), fill="white")
    for radius in range(120, 690, 60):
        d.arc((530-radius, 660-radius, 530+radius, 660+radius), 160, 330, fill="#28526B", width=6)
    f = ImageFont.truetype(BOLD, 51, layout_engine=ImageFont.Layout.RAQM)
    y = 420
    for line in wrap(d, headline, f, 610):
        d.text((48, y), line, font=f, fill="#FFFFFF")
        y += 96
    d.rounded_rectangle((35, 1020, 685, 1150), 20, fill="#FFD23F")
    sf = ImageFont.truetype(SINHALA, 29, layout_engine=ImageFont.Layout.RAQM)
    d.text((60, 1054), "අලුත්ම පුවත් සිංහලෙන්", font=sf, fill="#3E1620")
    d.text((45, 1200), "ORIGINAL NEWS GRAPHIC", font=ImageFont.truetype(LATIN, 20), fill="#9FB7CC")
    path = ROOT / f"slide{i}.png"
    im.save(path)
    return path

def main():
    concat = []
    for i, (tag, headline, narration) in enumerate(STORY, 1):
        image = slide(i, tag, headline)
        audio = ROOT / f"voice{i}.mp3"
        gTTS(narration, lang="si", slow=False, timeout=(10, 30)).save(str(audio))
        duration = subprocess.check_output(["ffprobe", "-v", "error", "-show_entries",
            "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(audio)], text=True)
        part = ROOT / f"part{i}.mp4"
        run(["ffmpeg", "-y", "-loop", "1", "-framerate", "25", "-i", str(image), "-i", str(audio),
             "-t", str(float(duration)+0.3), "-c:v", "libx264", "-preset", "veryfast",
             "-crf", "25", "-c:a", "aac", "-ar", "44100", "-b:a", "128k",
             "-pix_fmt", "yuv420p", "-shortest", str(part)])
        concat.append("file '" + str(part.resolve()) + "'")
    playlist = ROOT / "concat.txt"
    playlist.write_text("\n".join(concat)+"\n")
    output = ROOT / "SL_News_247_Sinhala_Voice_Demo.mp4"
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(playlist), "-c", "copy", str(output)])
    probe = subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "a",
        "-show_entries", "stream=codec_name", "-of", "default=nw=1", str(output)], text=True)
    if "aac" not in probe:
        raise RuntimeError("Narration is missing from final MP4")
    print("VOICE_VIDEO_READY", output)

if __name__ == "__main__":
    main()
