"""Vetted Sri Lankan classroom photo for education-policy stories only.

An archive photograph of a real primary classroom in Colombo; NOT footage of
a teachers' strike, union meeting or any specific article's event.

Copyright: Janith Dulshan, CC BY-SA 4.0
https://commons.wikimedia.org/wiki/File:Classroom_in_defence_servies_college.png
Any adapted image/video using this must meet attribution and share-alike terms.
"""
import base64
import hashlib
from io import BytesIO
from pathlib import Path

import requests
from PIL import Image

PHOTO = {
    'filename': 'Classroom_in_defence_servies_college.png',
    'source': 'https://commons.wikimedia.org/wiki/File:Classroom_in_defence_servies_college.png',
    'url': 'https://upload.wikimedia.org/wikipedia/commons/3/39/Classroom_in_defence_servies_college.png',
    'sha1': 'f6bc91bc70c7f76c759f145fc7351f71a31d260f',
    'creator': 'Janith Dulshan',
    'license': 'CC BY-SA 4.0',
    'license_url': 'https://creativecommons.org/licenses/by-sa/4.0/',
    'label_si': 'ශ්‍රී ලංකාවේ පාසල් පන්ති කාමරයක් — පසුබිම් දර්ශනය',
}
CACHE_FILE = Path(__file__).resolve().parent / 'assets/verified_photos/sri_lanka_classroom.png.b64'

def is_relevant(article):
    title = str(article.get('title_si', '')).casefold()
    school_staff = ('ගුරු', 'විදුහල්පති', 'teacher', 'principal')
    policy = ('වර්ජන', 'වැටුප්', 'අයවැය', 'වෘත්තීය', 'සමිති',
              'strike', 'salary', 'union', 'budget')
    return any(s in title for s in school_staff) and any(p in title for p in policy)

def select_education_photo(article, session=None):
    if not is_relevant(article):
        return None, None
    raw = None
    if CACHE_FILE.is_file():
        raw = base64.b64decode(CACHE_FILE.read_text(encoding='ascii').strip(), validate=True)
    else:
        session = session or requests
        headers = {
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/130 Safari/537.36',
            'Referer': PHOTO['source'],
            'Accept': 'image/png,image/*;q=0.8',
        }
        urls = [
            PHOTO['url'],
            'https://commons.wikimedia.org/wiki/Special:Redirect/file/' + PHOTO['filename'],
            'https://en.wikipedia.org/wiki/Special:Redirect/file/' + PHOTO['filename'],
        ]
        for url in urls:
            try:
                response = session.get(url, timeout=(5, 20), headers=headers)
                response.raise_for_status()
                raw = response.content
                if hashlib.sha1(raw).hexdigest() == PHOTO['sha1']:
                    break
                raw = None
            except requests.RequestException as exc:
                print('Vetted classroom image temporarily unavailable:', type(exc).__name__)
    if not raw or len(raw) > 5_000_000 or hashlib.sha1(raw).hexdigest() != PHOTO['sha1']:
        raise ValueError('Verified classroom image hash or availability failed')
    with Image.open(BytesIO(raw)) as source:
        source.verify()
    with Image.open(BytesIO(raw)) as source:
        if source.width < 900 or source.height < 600:
            raise ValueError('Original classroom image below approved quality')
        output = Path('output/verified_sri_lanka_classroom.jpg')
        output.parent.mkdir(exist_ok=True, parents=True)
        source.convert('RGB').save(output, quality=92)
    return str(output), {
        'source': PHOTO['source'], 'creator': PHOTO['creator'],
        'license': PHOTO['license'], 'license_url': PHOTO['license_url'],
        'label_si': PHOTO['label_si'], 'modified': 'cropped/resized; adaptation CC BY-SA 4.0',
    }
