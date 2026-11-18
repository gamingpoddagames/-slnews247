"""Original, clearly labelled animated Sinhala news bulletin, not event footage.

Uses verified news text, Sinhala TTS and our own graphic. It neither copies
broadcast clips nor purports to show the actual incident.
"""
import json
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def narration_for(article):
    from fast_news import complete_sentences, relevant_summary
    title = article.get('title_si', '').strip()
    # Prefer reviewed, fully sourced editorial detail rather than a short RSS
    # teaser. Use original Sinhala wording, not the publisher's voice/audio.
    from editorial import brief_for
    reviewed = brief_for(article) if article.get('id') and article.get('link') else {}
    source_text = reviewed.get('body_si') or article.get('summary_si', '')
    summary = complete_sentences(source_text, 1250)
    if not summary or not relevant_summary(title, summary):
        raise ValueError('Factual, matching Sinhala narration required')
    clauses = []
    for sentence in __import__('re').findall(r'[^.!?।]+[.!?।]+', summary):
        if len(' '.join(clauses + [sentence])) > 580:
            break
        clauses.append(sentence.strip())
    if not clauses:
        raise ValueError('No complete, suitably short narration sentence')
    return title + '. ' + ' '.join(clauses)


def render_bulletin(article, output_path='output/animated_news_bulletin.mp4'):
    """Generate a moving 9:16 graphic with real Sinhala voice narration."""
    from image import news_card, draw_mixed
    from voice import create_voice
    from fast_news import complete_sentences
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    voice_path = output.with_suffix('.mp3')
    script = narration_for(article)
    if not create_voice(script, str(voice_path)):
        raise RuntimeError('Sinhala voice generation unavailable')

    # Sound must have a real duration and audio track before video encoding.
    from mutagen.mp3 import MP3
    duration = float(MP3(str(voice_path)).info.length)
    if not 2 <= duration <= 90:
        raise ValueError('Invalid narration audio or overly long bulletin')

    # Make original static artwork then add actual motion with FFmpeg zoompan.
    poster_path = news_card(article)
    with Image.open(poster_path) as original:
        poster = original.convert('RGB')
        background = Image.new('RGB', (1080,1920), '#061335')
        background.paste(poster, (0,160))
    canvas = ImageDraw.Draw(background)
    canvas.rectangle((0,0,1080,26),fill='#ed6826')
    canvas.rectangle((0,1580,1080,1920),fill='#091b45')
    canvas.line((72,1610,1008,1610), fill='#2d76cf',width=5)
    draw_mixed(canvas,(80,1680),'සිංහල පුවත් සාරාංශ වීඩියෝව',48,fill='white',bold=True)
    draw_mixed(canvas,(80,1756),'සිද්ධියේ සැබෑ වීඩියෝ දර්ශන නොවේ',32,fill='#b4d2fc')
    label_path = str(output.with_suffix('.png'))
    background.save(label_path)

    # Zoom varies gradually with frame number; this is an animated bulletin,
    # not a still image relabelled as event footage.
    cmd = ['ffmpeg','-y','-loglevel','error','-loop','1','-framerate','20','-i',label_path,
           '-i',str(voice_path),
           '-filter_complex',
           "[0:v]zoompan=z='min(zoom+0.00018,1.09)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=720x1280:fps=20,format=yuv420p[v]",
           '-map','[v]','-map','1:a:0','-t',str(duration),'-r','20',
           '-c:v','libx264','-preset','veryfast','-crf','25',
           '-c:a','aac','-b:a','96k','-movflags','+faststart',
           '-shortest',str(output)]
    subprocess.run(cmd,check=True,timeout=240,capture_output=True)
    if not output.is_file() or output.stat().st_size < 20000:
        raise RuntimeError('Bulletin video not created')
    return str(output)
