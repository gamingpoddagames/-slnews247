"""Clearly labelled real subject photos for news where exact event media is unavailable.
Never depict a stock photo as the actual incident. Use narrowly matched neutral subjects,
not stock faces for allegations, victims, or patients.
"""
import os, re, hashlib
from functools import lru_cache
from pathlib import Path
from io import BytesIO
from urllib.parse import urlsplit
import requests
from PIL import Image

# Sinhala title trigger, English search, required subject words in Pexels caption,
# on-image label. Each rule refers to a concrete visual subject.
RULES = (
    (('වෘත්තීය පුහුණුව','වෘත්තීය අධ්‍යාපන'), 'vocational training workshop tools', ('workshop','tools','training','welding','carpentry'), 'වෘත්තීය පුහුණුව'),
    (('මැතිසබ','පාර්ලිමේන්තු'), 'parliament building', ('parliament',), 'පාර්ලිමේන්තු පුවත'),
    (('ක්‍රිකට්','ක්රිකට්'), 'cricket bat ball pitch', ('cricket',), 'ක්‍රිකට්'),
    (('කාලගුණ','වැසි','වර්ෂාව'), 'rain clouds rainfall', ('rain','rainfall','storm clouds'), 'කාලගුණය'),
    (('එළවළු','එලවළු'), 'fresh vegetables market', ('vegetables',), 'එළවළු'),
    (('තේ අපනයන','තේ මිල','තේ නිෂ්පාදන'), 'tea plantation tea leaves', ('tea leaves','tea plantation','tea field'), 'තේ නිෂ්පාදනය'),
    (('ඉන්ධන මිල','ඉන්ධන සැපයුම','පෙට්‍රල්'), 'fuel pump petrol station', ('fuel','gas station','petrol'), 'ඉන්ධන'),
    (('විදුලි බිල','විදුලි ගාස්තු','විදුලි සැපයුම'), 'electric power transmission tower', ('power line','transmission','electricity'), 'විදුලි සැපයුම'),
    (('රන් මිල','රත්‍රන් මිල'), 'gold bars bullion', ('gold bar','bullion','gold bars'), 'රන් මිල'),
    (('සහල් මිල','සහල් ආනයන','වී මිල'), 'uncooked rice grains', ('rice grains','uncooked rice','raw rice'), 'සහල්'),
    (('දුම්රිය සේවා','දුම්රිය ගාස්තු','දුම්රිය ධාවන'), 'railway tracks train', ('railway','train tracks','railroad'), 'දුම්රිය සේවා'),
    (('කොටස් වෙළෙඳපොළ','කොටස් වෙළඳපොළ'), 'stock market financial chart screen', ('stock market','stock trading','financial chart'), 'කොටස් වෙළෙඳපොළ'),
)
SENSITIVE = ('මරණ','මරු','ඝාත','අනතුර','ප්‍රහාර','අත්අඩංගු','අල්ලයි','සැකකරු','අතවර','අපරාධ','තුවාල','සුළි කුණාටු','විපත','ගංවතුර','ගිනි','වංචා')

def rule_for(title):
    if any(w in title for w in SENSITIVE):
        return None
    return next((r for r in RULES if any(w in title for w in r[0])), None)

@lru_cache(maxsize=64)
def subject_photo_set(title, article_id):
    rule = rule_for(title)
    key = os.getenv('PEXELS_API_KEY','').strip()
    if not rule or not key:
        return ()
    _, query, required, label = rule
    try:
        response = requests.get('https://api.pexels.com/v1/search',
            headers={'Authorization':key},params={'query':query,'per_page':15,'orientation':'landscape'},timeout=(4,10))
        response.raise_for_status()
        items = response.json().get('photos',[])
    except (requests.RequestException, ValueError, TypeError):
        return ()
    output = []
    for item in items:
        alt = str(item.get('alt') or '').lower()
        if not any(re.search(r'\b'+re.escape(term)+r'\b',alt) for term in required):
            continue
        # Avoid faces/portraits in editorial context; training shots must describe
        # the workshop or actual equipment rather than a person's identity.
        if any(w in alt for w in ('portrait','selfie','close-up of a face')):
            continue
        url = (item.get('src') or {}).get('large') or ''
        source = item.get('url') or ''
        if urlsplit(url).scheme != 'https' or urlsplit(url).hostname != 'images.pexels.com':
            continue
        if not source.startswith('https://www.pexels.com/photo/'):
            continue
        creator = str(item.get('photographer') or '').strip()[:100]
        if not creator:
            continue
        try:
            path = Path('output') / ('subject_'+hashlib.sha256((str(article_id)+url).encode()).hexdigest()[:24]+'.jpg')
            if not path.is_file():
                data = bytearray()
                with requests.get(url,stream=True,allow_redirects=False,timeout=(4,12)) as resp:
                    if resp.status_code != 200:
                        continue
                    for chunk in resp.iter_content(65536):
                        data.extend(chunk)
                        if len(data)>10_000_000:
                            raise ValueError('Photo exceeds size limit')
                with Image.open(BytesIO(data)) as im:
                    im.verify()
                with Image.open(BytesIO(data)) as im:
                    if im.width<600 or im.height<400:
                        continue
                    path.parent.mkdir(exist_ok=True)
                    im.convert('RGB').save(path,quality=90)
            output.append((str(path),'licensed_subject_stock',{'creator':creator,'source':source,
                'license':'Pexels License','license_url':'https://www.pexels.com/license/',
                'label_si':'Stock photo'}))
            if len(output)>=3:
                break
        except (requests.RequestException,OSError,ValueError,TypeError):
            continue
    return tuple(output)
