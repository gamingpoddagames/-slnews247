"""Media holds and readable photo-first layout behaviour."""
import os
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch


class MediaFirstDesignTests(unittest.TestCase):
    def test_thirteen_hour_old_story_is_not_latest_news(self):
        from fast_news import parse_feed
        now = time.time()
        date = datetime.fromtimestamp(now - 13*3600, timezone.utc).isoformat()
        xml = (f'<rss><channel><item><title>ශ්‍රී ලංකාවේ පුවතක්</title>'
               f'<link>https://example.com/old</link><pubDate>{date}</pubDate>'
               '</item></channel></rss>')
        stories, total = parse_feed(xml.encode(), 'test', now)
        self.assertEqual(total, 1)
        self.assertEqual(stories, [])

    def test_unapproved_video_never_enters_frame_decoder(self):
        from real_photo import select_event_video_frame
        with patch('media.choose_video', return_value=None), \
             patch('subprocess.run') as decoder:
            self.assertIsNone(select_event_video_frame({'id': 'story'}))
        decoder.assert_not_called()

    def test_failed_video_decode_does_not_reuse_previous_frame(self):
        import subprocess
        import hashlib
        from real_photo import select_event_video_frame
        previous = os.getcwd()
        with tempfile.TemporaryDirectory() as folder:
            try:
                os.chdir(folder)
                output = Path('output/event_frame_' + hashlib.sha256(
                    b'story').hexdigest()[:24] + '.jpg')
                output.parent.mkdir()
                output.write_bytes(b'old frame')
                with patch('media.choose_video', return_value='approved.mp4'), \
                     patch('subprocess.run', side_effect=subprocess.CalledProcessError(1, 'ffmpeg')):
                    with self.assertRaises(subprocess.CalledProcessError):
                        select_event_video_frame({'id': 'story'})
                self.assertFalse(output.exists())
            finally:
                os.chdir(previous)

    def test_reel_photo_disappearing_at_render_time_is_a_hold(self):
        from animated_bulletin import build_scene_images
        with tempfile.TemporaryDirectory() as folder, \
             patch.dict(os.environ, {'REELS_REQUIRE_EVENT_MEDIA': 'false'}), \
             patch('real_photo.select_real_photo', return_value=(None, None, None)), \
             patch('animated_bulletin._slide') as render:
            with self.assertRaisesRegex(ValueError, 'photo required'):
                build_scene_images({'require_event_media': True}, 'script', folder)
        render.assert_not_called()

    def test_complete_bold_headlines_fit_readable_light_panel(self):
        from PIL import Image, ImageDraw
        from image import _fitted_lines, mixed_width
        draw = ImageDraw.Draw(Image.new('RGB', (1080, 1350)))
        titles = [
            'ශ්‍රී ලංකා මහ බැංකුවේ පුවත් සහ නිල නිවේදන',
            'දිස්ත්‍රික්ක කිහිපයකට තද වැසි ඇතිවිය හැකි බව කාලගුණ විද්‍යා දෙපාර්තමේන්තුව දැනුම් දෙයි',
            'A කණ්ඩායම් ක්‍රිකට් ඉතිහාසයේ වේගවත්ම ශතකය වෛභව් සූර්යවංශි ගේ නමට',
        ]
        for title in titles:
            size, lines, step = _fitted_lines(draw, title, 888, 310, range(72, 31, -2))
            self.assertEqual(' '.join(lines), title)
            self.assertGreaterEqual(size, 32)
            self.assertLessEqual(step * len(lines), 310)
            self.assertTrue(all(mixed_width(draw, line, size, bold=True) <= 888
                                for line in lines))
