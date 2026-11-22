"""Original event-specific Sinhala infographic graphics for SL News 24/7.

This renders accurate news facts and topic-specific vector diagrams. These
graphics do not impersonate real footage or photographs of a reported event.
Only the article's own checked wording is displayed; no unrelated stock photos.
"""
import re
from PIL import ImageDraw

THEMES = (
    ("education", ("ගුරු", "විදුහල්පති", "පාසල්", "අධ්‍යාපන", "ගුරුවර", "school", "teacher"), "අධ්‍යාපන"),
    ("finance", ("මහ බැංකු", "මහබැංකු", "පොලී", "බැංකු", "අයවැය", "උද්ධමන", "රුපියල්", "මිල", "bank", "budget"), "ආර්ථික"),
    ("weather", ("කාලගුණ", "වැසි", "සුළි", "ගංවතුර", "නායය", "weather", "rain"), "කාලගුණ"),
    ("transport", ("දුම්රිය", "බස්", "මාර්ග", "ගුවන්", "රථවාහන", "rail", "road"), "ගමනාගමන"),
    ("health", ("රෝහල", "වෛද්‍ය", "සෞඛ්‍ය", "රෝග", "hospital", "health"), "සෞඛ්‍ය"),
    ("sport", ("ක්‍රිකට්", "පාපන්දු", "තරග", "ක්‍රීඩා", "cricket", "sport"), "ක්‍රීඩා"),
    ("justice", ("පොලිසිය", "අත්අඩංගුව", "අධිකරණ", "නඩුව", "වැටලීම", "මත්ද්‍රව්‍ය", "police", "court"), "නීතිය"),
    ("government", ("පාර්ලිමේන්තු", "අමාත්‍ය", "කැබිනට්", "රජය", "මැතිවරණ", "parliament", "cabinet"), "රාජ්‍ය"),
)
MONTHS = ("ජනවාරි", "පෙබරවාරි", "මාර්තු", "අප්‍රේල්", "මැයි", "ජූනි",
          "ජූලි", "අගෝස්තු", "සැප්තැම්බර්", "ඔක්තෝබර්", "නොවැම්බර්", "දෙසැම්බර්")


def story_theme(article):
    title = str(article.get("title_si", "")).casefold()
    for name, keys, label in THEMES:
        if any(word in title for word in keys):
            return name, label
    return "news", "ප්‍රධාන පුවත"


def story_facts(article, limit=3):
    """Extract only complete, verifiable sentences from supplied newsroom text."""
    summary = str(article.get("summary_si", "")).strip()
    if not summary:
        return []
    # Decimal points have no following whitespace, so these remain intact.
    pieces = re.split(r"(?<=[.!?।])\s+", summary)
    result = []
    for sentence in pieces:
        sentence = sentence.strip()
        if 24 <= len(sentence) <= 380 and sentence[-1:] in ".!?।" and sentence not in result:
            result.append(sentence)
        if len(result) >= limit:
            break
    return result


def highlight(article):
    """Show the actual headline's prominent number/date, not a made-up metric."""
    title = str(article.get("title_si", ""))
    for name in MONTHS:
        found = re.search(re.escape(name) + r"\s*(\d{1,2})(?!\d)", title)
        if found:
            return found.group(1), name
    found = re.search(r"(?<!\d)(\d+(?:[.,]\d+)?\s*%)(?!\d)", title)
    if found:
        return found.group(1).replace(" ", ""), "ප්‍රධාන අගය"
    found = re.search(r"(?<!\d)(\d+(?:[.,]\d+)?)(?!\d)", title)
    if found:
        return found.group(1), "පුවතේ අගය"
    return None, None


def _icon(draw, kind, x, y, scale, color):
    """Draw a recognisable but non-photorealistic topic symbol."""
    s = scale
    def rect(a,b,c,d,fill=None,outline=None,width=3):
        draw.rounded_rectangle((x+a*s,y+b*s,x+c*s,y+d*s),
                               radius=max(2,int(8*s)), fill=fill, outline=outline,
                               width=max(1,int(width*s)))
    if kind == "education":
        draw.polygon([(x+8*s,y+54*s),(x+96*s,y+5*s),(x+184*s,y+54*s)], fill=color)
        rect(24,55,168,168,fill="#1a3760",outline=color,width=5)
        for xx in (47,91,135):
            rect(xx-12,76,xx+13,105,fill="#f6c04e")
        rect(74,120,116,168,fill="#f6c04e")
    elif kind == "finance":
        draw.polygon([(x+7*s,y+55*s),(x+97*s,y+5*s),(x+187*s,y+55*s)],fill=color)
        rect(17,59,177,75,fill=color)
        for xx in (33,75,117,159):
            rect(xx,79,xx+17,159,fill="#d2e6ef")
        rect(9,162,185,181,fill=color)
    elif kind == "weather":
        for xx,yy,rr in ((63,91,41),(107,64,54),(153,98,43)):
            draw.ellipse((x+(xx-rr)*s,y+(yy-rr)*s,x+(xx+rr)*s,y+(yy+rr)*s),fill=color)
        rect(42,103,177,137,fill=color)
        for xx in (65,103,141):
            draw.line((x+xx*s,y+147*s,x+(xx-11)*s,y+184*s),
                      fill="#69d4fa",width=max(2,int(7*s)))
    elif kind == "transport":
        rect(23,27,174,146,fill=color)
        rect(40,46,86,93,fill="#1a3760")
        rect(109,46,156,93,fill="#1a3760")
        for xx in (52,142):
            draw.ellipse((x+(xx-17)*s,y+137*s,x+(xx+17)*s,y+173*s),fill="#eaf3fc")
    elif kind == "health":
        rect(36,42,154,181,fill=color)
        rect(81,17,110,112,fill="#f7ffff")
        rect(49,50,144,79,fill="#f7ffff")
        rect(82,132,111,181,fill="#1a3760")
    elif kind == "sport":
        draw.ellipse((x+40*s,y+42*s,x+166*s,y+168*s),fill=color)
        draw.arc((x+57*s,y+53*s,x+150*s,y+154*s),45,260,fill="#1a3760",width=max(3,int(8*s)))
    elif kind == "justice":
        draw.polygon([(x+96*s,y+7*s),(x+169*s,y+38*s),(x+155*s,y+132*s),
                      (x+96*s,y+181*s),(x+37*s,y+132*s),(x+23*s,y+38*s)],fill=color)
        draw.line((x+96*s,y+54*s,x+96*s,y+132*s),fill="#1a3760",width=max(3,int(10*s)))
        draw.line((x+61*s,y+79*s,x+132*s,y+79*s),fill="#1a3760",width=max(3,int(8*s)))
    else:
        rect(31,31,160,164,fill=color)
        for yy in (68,97,126):
            draw.line((x+52*s,y+yy*s,x+139*s,y+yy*s),fill="#1a3760",width=max(2,int(7*s)))


def draw_story_hero(canvas, article, bounds, scene=0, fact=None):
    """Draw an entirely original topical data graphic in an existing news card."""
    from image import draw_mixed, fit_headline, latin_font
    x0,y0,x1,y1=map(int,bounds)
    w,h=x1-x0,y1-y0
    if w<=0 or h<=0:
        raise ValueError("Invalid hero graphic bounds")
    draw=ImageDraw.Draw(canvas)
    bg="#071b35"
    draw.rectangle(bounds,fill=bg)
    for k in range(0,h,7):
        a=k/max(1,h)
        draw.rectangle((x0,y0+k,x1,min(y1,y0+k+7)),
                       fill=(int(7+8*a),int(27+24*a),int(53+25*a)))
    topic,label=story_theme(article)
    gold="#f5c451"
    accent="#4ac3d8"
    unit=min(w/988,h/752)
    # Topic frame and simple drawn symbol reflect this story's subject.
    pad=int(46*unit)
    bx=x0+pad
    by=y0+int(158*unit)
    icon_size=int(180*unit)
    draw.rounded_rectangle((bx,by,bx+int(230*unit),by+int(232*unit)),
                           radius=int(32*unit),fill="#1b3d65",outline="#447ba0",width=max(2,int(3*unit)))
    _icon(draw,topic,bx+int(23*unit),by+int(17*unit),unit,gold)
    # Safe wide facts area, with live data extracted from THIS headline.
    num,number_label=highlight(article)
    val_x=x0+int(342*unit)
    if num:
        from image import mixed_width
        fs=max(40,int(125*unit))
        width_avail=x1-val_x-int(32*unit)
        while fs>32 and mixed_width(draw,num,fs,bold=True)>width_avail:
            fs-=4
        draw_mixed(draw,(val_x,by+int(120*unit)),num,fs,bold=True,fill=gold)
        draw_mixed(draw,(val_x,by+int(175*unit)),number_label,
                   max(18,int(32*unit)),fill="white",bold=True)
    else:
        draw_mixed(draw,(val_x,by+int(95*unit)),label,
                   max(26,int(51*unit)),fill=gold,bold=True)
    # The core story facts occupy the visual, not a tiny unrelated footer.
    facts=story_facts(article)
    selected=fact if fact else (facts[scene%len(facts)] if facts else str(article.get('title_si','')))
    fy=y0+int(494*unit)
    fx=x0+int(55*unit)
    fw=w-int(110*unit)
    fh=max(60,y1-fy-int(24*unit))
    draw.rounded_rectangle((fx,fy,x1-int(44*unit),y1-int(18*unit)),
                           radius=max(12,int(17*unit)),fill="#183a5e")
    draw.rectangle((fx,fy,fx+max(4,int(7*unit)),y1-int(18*unit)),fill=accent)
    try:
        size,lines,step=fit_headline(draw,selected,width=fw-int(42*unit),
                                     max_height=fh-int(16*unit),
                                     start_size=max(18,int(32*unit)),
                                     min_size=max(14,int(16*unit)))
        yy=fy+int(35*unit)
        for line in lines:
            draw_mixed(draw,(fx+int(28*unit),yy),line,size,
                       fill="white",bold=True)
            yy+=step
    except ValueError:
        # If an unusually long factual sentence cannot fit, show an
        # untruncated verified headline, never fabricate or cut a fact.
        compact=str(article.get('title_si',''))
        size,lines,step=fit_headline(draw,compact,width=fw-int(42*unit),
                                    max_height=fh-int(16*unit),
                                    start_size=max(18,int(31*unit)),
                                    min_size=14)
        yy=fy+int(35*unit)
        for line in lines:
            draw_mixed(draw,(fx+int(28*unit),yy),line,size,fill="white")
            yy+=step
    return {"topic":topic,"label":label,"fact":selected,"highlight":num}
