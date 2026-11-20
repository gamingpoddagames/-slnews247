"""Original topic-specific illustrations for news cards (not event photographs).

Publisher images may be discovered elsewhere for rights review, but never copied
automatically. These vector scenes are generated locally and labelled accurately.
"""
from pathlib import Path
import hashlib
import re
from PIL import Image, ImageDraw, ImageFont

CATEGORIES = (
    ("education", ("විභාග", "පාසල්", "සිසු", "අධ්‍යාපන", "ශිෂ්‍ය", "exam", "school")),
    ("weather", ("වැසි", "කාලගුණ", "සුළං", "ගංවතුර", "නායයෑ", "weather", "rain")),
    ("health", ("රෝහල", "වෛද්‍ය", "සෞඛ්‍ය", "රෝග", "health", "hospital")),
    ("transport", ("මාර්ග", "බස්", "දුම්රිය", "අධිවේගී", "රිය අනතුර", "train", "road")),
    ("economy", ("මිල", "ආර්ථික", "බදු", "රුපියල්", "වෙළඳ", "බැංකු", "price", "economy")),
    ("sport", ("ක්‍රිකට්", "පාපන්දු", "තරග", "ක්‍රීඩා", "cricket", "sports")),
    ("government", ("පාර්ලිමේන්තු", "අමාත්‍ය", "ජනාධිපති", "රජය", "මැතිවරණ", "parliament")),
    ("energy", ("විදුලි", "ඉන්ධන", "ගෑස්", "බලශක්ති", "fuel", "power")),
)

def topic_for(article):
    value = (str(article.get("title_si", "")) + " " + str(article.get("summary_si", ""))).casefold()
    for category, keywords in CATEGORIES:
        if any(keyword in value for keyword in keywords):
            return category
    return "general"

def original_illustration(article):
    """Make a relevant, unambiguously illustrative 988x752 image, no external assets."""
    title = str(article.get("title_si", "")).strip()
    if not title:
        raise ValueError("Cannot illustrate an empty news headline")
    topic = topic_for(article)
    width, height = 988, 752
    colors = {"education": (34, 86, 156), "weather": (23, 92, 137),
              "health": (22, 119, 112), "transport": (54, 90, 130),
              "economy": (103, 69, 133), "sport": (24, 111, 86),
              "government": (95, 73, 124), "energy": (148, 91, 30),
              "general": (45, 85, 144)}
    base = colors[topic]
    image = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(image)
    for y in range(height):
        k = y / height
        draw.line((0, y, width, y), fill=tuple(int(c * (1-k) + 10*k) for c in base))
    # Unique abstract rings, with stable geometry per headline.
    digest = hashlib.sha256(title.encode("utf-8")).digest()
    for i in range(4):
        x = 135 + (digest[i] * 3) % 750
        y = 90 + (digest[i+4] * 2) % 520
        radius = 85 + digest[i+8] % 140
        draw.ellipse((x-radius, y-radius, x+radius, y+radius),
                     outline=(90, 151, 189), width=3)
    white, gold, dark = "#eaf8ff", "#ffcf46", "#10243e"
    # Subject pictograms deliberately convey a topic, not a fabricated incident.
    if topic == "education":
        draw.rounded_rectangle((215, 175, 780, 600), 25, fill=white)
        draw.rectangle((260, 260, 720, 280), fill=base)
        for y in (340, 395, 450):
            draw.rounded_rectangle((265, y, 675, y+17), 8, fill="#88a8bf")
        draw.rounded_rectangle((570, 490, 730, 555), 13, fill=gold)
    elif topic == "weather":
        draw.ellipse((320, 175, 570, 425), fill=white)
        draw.ellipse((460, 130, 740, 430), fill=white)
        draw.rounded_rectangle((250, 310, 765, 430), 60, fill=white)
        for x in (315, 435, 555, 675):
            draw.line((x, 475, x-65, 590), fill=gold, width=20)
    elif topic == "health":
        draw.rounded_rectangle((290, 155, 700, 625), 45, fill=white)
        draw.rectangle((455, 230, 535, 525), fill="#d8364a")
        draw.rectangle((340, 340, 650, 420), fill="#d8364a")
    elif topic == "transport":
        draw.polygon([(320, 655), (465, 145), (545, 145), (710, 655)], fill="#334759")
        for y in (250, 380, 530):
            draw.line((500, y, 500, y+68), fill=gold, width=19)
        draw.line((170, 660, 820, 660), fill=white, width=12)
    elif topic == "economy":
        draw.line([(235, 590), (370, 440), (500, 500), (640, 305), (750, 200)],
                  fill=gold, width=30, joint="curve")
        draw.polygon([(680, 195), (795, 150), (768, 290)], fill=gold)
        for x, h in ((290, 210), (430, 310), (570, 270), (710, 410)):
            draw.rounded_rectangle((x-45, 635-h, x+45, 635), 12, fill=white)
    elif topic == "sport":
        draw.ellipse((285, 155, 715, 585), fill=white)
        for x, y in ((400, 280), (560, 280), (350, 420), (610, 420)):
            draw.ellipse((x-26, y-26, x+26, y+26), fill=base)
        draw.ellipse((445, 325, 555, 435), fill=base)
    elif topic == "government":
        draw.polygon([(200, 305), (500, 130), (800, 305)], fill=white)
        for x in (265, 390, 515, 640):
            draw.rounded_rectangle((x, 335, x+60, 580), 9, fill=white)
        draw.rounded_rectangle((185, 590, 815, 650), 12, fill=gold)
    elif topic == "energy":
        draw.polygon([(530, 120), (315, 445), (475, 445),
                      (415, 640), (720, 330), (545, 330)], fill=gold)
    else:
        draw.ellipse((315, 145, 680, 510), outline=white, width=25)
        draw.arc((210, 200, 785, 575), 5, 170, fill=gold, width=28)
        draw.arc((210, 200, 785, 575), 185, 350, fill=gold, width=28)
        draw.line((225, 620, 770, 620), fill=white, width=18)

    # Do not use this scene as photographic evidence; news_card adds Sinhala label.
    Path("output").mkdir(exist_ok=True)
    safe_id = re.sub(r"[^A-Za-z0-9_-]", "", str(article.get("id", "")))[:70] or hashlib.sha1(title.encode()).hexdigest()[:16]
    path = Path("output") / ("illustration_" + safe_id + ".png")
    image.save(path, optimize=True)
    return str(path)
