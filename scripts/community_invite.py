"""Daily SL NEWS community invitation, using existing owner-authorized channels."""
import json
import os
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode
from zoneinfo import ZoneInfo
import requests
from PIL import Image, ImageDraw, ImageOps
from image import broadcast_background, crimson_panel, latin_font, draw_mixed, mixed_width

STATE = Path('data/community_invite_delivery.json')
PAGE = 'https://www.facebook.com/1020689164470492'
GROUP = 'https://www.facebook.com/share/g/1Mfe9tJaMa/'
MESSAGES = [
    'නවතම පුවත් මඟ නොහැර දැනගන්න SL NEWS 24/7 සමඟ එක්වන්න.',
    'ශ්‍රී ලංකාවේ සහ ලෝකයේ වැදගත් පුවත් එකම තැනකින්.',
    'අද දවසේ ඔබට වැදගත්ම පුවත කුමක්ද? ඔබේ අදහස අප සමඟ බෙදාගන්න.',
    'පැය විසිහතර පුරාම පුවත් දැනගන්න අප සමඟ රැඳී සිටින්න.',
    'දේශීය හා විදේශීය පුවත් සිංහලෙන්. ඔබේ අදහස් අපි අගය කරනවා.',
    'දැනුවත් සමාජයක් වෙනුවෙන් වැදගත් පුවත් බෙදාගමු.',
    'නවතම පුවත් සමඟ අප හා එක්වන්න.'
]

def render(day):
    canvas = broadcast_background((1080, 1350), (32, 56, 1048, 1295), 88)
    canvas.paste(crimson_panel((988, 1212)), (46, 70))
    logo = Path('assets/logo.png')
    try:
        with Image.open(logo) as im:
            im = ImageOps.contain(im.convert('RGBA'), (320, 320))
            canvas.paste(im, ((1080-im.width)//2, 120), im)
    except (OSError, ValueError):
        # Original brand mark, not a borrowed or invented third-party logo.
        brand = ImageDraw.Draw(canvas)
        brand.rounded_rectangle((375, 120, 705, 430), radius=55, fill='#18324e', outline='#ffe24a', width=5)
        brand.text((540, 230), 'SL NEWS', font=latin_font(53, bold=True), fill='white', anchor='mm')
        brand.text((540, 330), '24/7', font=latin_font(92, bold=True), fill='#ffe24a', anchor='mm')
    draw = ImageDraw.Draw(canvas)
    def center(line, baseline, size, color):
        x = (1080 - mixed_width(draw, line, size, bold=True)) / 2
        draw_mixed(draw, (x, baseline), line, size, fill=color, bold=True)
    draw.text((540, 470), 'SL NEWS 24/7', font=latin_font(65, bold=True), fill='white', anchor='mm')
    center('පැය විසිහතර පුරාම', 580, 52, '#ffe24a')
    center('නවතම පුවත් සඳහා', 690, 53, 'white')
    center('අප සමඟ එක්වන්න!', 780, 64, '#ffe24a')
    draw.rounded_rectangle((125, 850, 955, 1030), radius=35, fill='#18324e', outline='#ffe24a', width=4)
    draw.text((540, 900), 'FOLLOW  •  LIKE', font=latin_font(54, bold=True), fill='white', anchor='mm')
    draw.text((540, 972), 'COMMENT  •  SHARE', font=latin_font(48, bold=True), fill='#ffe24a', anchor='mm')
    center('ඔබේ අදහස් අපට කියන්න', 1130, 40, 'white')
    draw.text((540, 1215), day.strftime('%d.%m.%Y'), font=latin_font(29, bold=True), fill='white', anchor='mm')
    path = Path('output/community_invite.png')
    path.parent.mkdir(exist_ok=True)
    canvas.save(path)
    return path

def main():
    day = datetime.now(ZoneInfo('Asia/Colombo')).date()
    key = day.isoformat()
    text = ('SL NEWS 24/7\n\n' + MESSAGES[day.weekday()] +
            '\n\nඅපේ පිටුව Follow කරන්න. ප්‍රයෝජනවත් පුවත් Like කරන්න, ඔබේ අදහස් Comment කරන්න සහ මිතුරන් සමඟ Share කරන්න.\n\n' + PAGE)
    path = render(day)
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    record = state.setdefault(key, {})
    def save():
        STATE.parent.mkdir(exist_ok=True)
        temp = STATE.with_suffix('.tmp')
        temp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + '\n')
        temp.replace(STATE)
    for dest in ('facebook', 'telegram'):
        if dest in record:
            continue
        names = ('FB_PAGE_ID','FB_PAGE_TOKEN') if dest == 'facebook' else ('TG_TOKEN','TG_CHAT_ID')
        if not all(os.getenv(n) for n in names):
            print(dest + ': missing credentials')
            continue
        record[dest] = {'status':'started'}
        save()
        try:
            if dest == 'facebook':
                with path.open('rb') as photo:
                    response = requests.post('https://graph.facebook.com/v22.0/'+os.environ['FB_PAGE_ID']+'/photos',
                        data={'access_token':os.environ['FB_PAGE_TOKEN'],'caption':text},
                        files={'source':photo},timeout=(5,60))
                payload = response.json()
                ident = (payload.get('post_id') or payload.get('id')) if response.ok else None
                link = 'https://www.facebook.com/' + str(ident) if ident else None
            else:
                post = record.get('facebook',{}).get('url') or PAGE
                share = 'https://www.facebook.com/sharer/sharer.php?' + urlencode({'u':post})
                buttons = {'inline_keyboard':[[{'text':'Follow SL NEWS 24/7','url':PAGE}],
                                              [{'text':'Share to Facebook (choose group)','url':share}],
                                              [{'text':'Open our Facebook group','url':GROUP}]]}
                with path.open('rb') as photo:
                    response = requests.post('https://api.telegram.org/bot'+os.environ['TG_TOKEN']+'/sendPhoto',
                        data={'chat_id':os.environ['TG_CHAT_ID'],'caption':text,'reply_markup':json.dumps(buttons)},
                        files={'photo':photo}, timeout=(5,45))
                payload = response.json()
                ident = payload.get('result',{}).get('message_id') if response.ok and payload.get('ok') else None
                link = None
            record[dest] = {'status':'accepted' if ident else 'rejected',
                            'id':str(ident) if ident else None,'url':link}
        except Exception:
            record[dest] = {'status':'unconfirmed'}
        save()
        print(dest + ': ' + record[dest]['status'])
    if any(record.get(d,{}).get('status') != 'accepted' for d in ('facebook','telegram')):
        raise RuntimeError('Community invitation delivery needs review; do not blindly resend')

if __name__ == '__main__':
    main()
