"""Render a real MP4 without posting, to catch FFmpeg/font regressions."""
import subprocess
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

from animated_bulletin import render_bulletin

def create_demo_voice(_script, path):
    # Real playable synthetic audio, not a mocked success response.
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'lavfi',
                    '-i', 'sine=frequency=440:sample_rate=44100',
                    '-t', '6', '-c:a', 'libmp3lame', path],
                   check=True, timeout=40)
    return True

def main():
    article = {
        'id': 'production-render-smoke-test',
        'title_si': 'මාතර ප්‍රදේශයේ වැදගත් පුවතක්',
        'summary_si': ('මාතර ප්‍රදේශයේ වැදගත් සිදුවීමක් සම්බන්ධයෙන් අදාළ නිලධාරීන් සාකච්ඡාවක් පවත්වා තිබේ. '
                       'මාතර ප්‍රදේශයේ තවත් කරුණු සොයා බැලීම සඳහා පරීක්ෂණ සිදු කරන බව නිලධාරීන් සඳහන් කළහ.'),
        'published': time.time(),
        'link': 'https://example.com/smoke',
    }
    with tempfile.TemporaryDirectory() as directory:
        path = str(Path(directory) / 'smoke.mp4')
        with patch('voice.create_voice', side_effect=create_demo_voice), \
             patch('media.choose_photo', return_value=None):
            render_bulletin(article, path)
        probe = subprocess.run(
            ['ffmpeg','-v','error','-i',path,'-f','null','-'],
            timeout=60, text=True, capture_output=True)
        if probe.returncode != 0:
            raise RuntimeError('MP4 decode validation failed: ' + probe.stderr[-800:])
        if Path(path).stat().st_size < 20000:
            raise RuntimeError('MP4 unexpectedly small')
        print('3-scene original news video rendered and decoded successfully:', Path(path).stat().st_size)

if __name__ == '__main__':
    main()
