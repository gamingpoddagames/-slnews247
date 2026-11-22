import base64
import hashlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from PIL import Image
from education_photo import CACHE_FILE, PHOTO, is_relevant, select_education_photo


class EducationPhotoTests(unittest.TestCase):
    ARTICLE = {
        'id': 'education-unions',
        'title_si': 'නොවැම්බර් 30 ගුරු විදුහල්පති වර්ජනයක් සැලසුම්',
        'summary_si': 'ගුරු හා විදුහල්පතිවරු වෘත්තීය ක්‍රියාමාර්ගයකට සැලසුම් කර තිබේ.',
    }

    def test_real_commons_photo_pinned_with_exact_verified_hash(self):
        self.assertTrue(CACHE_FILE.is_file(), 'Vetted original should ship with project')
        raw = base64.b64decode(CACHE_FILE.read_text(encoding='ascii').strip(), validate=True)
        self.assertEqual(hashlib.sha1(raw).hexdigest(), PHOTO['sha1'])
        with Image.open(io.BytesIO(raw)) as original:
            self.assertEqual(original.size, (1536, 1020))

    def test_education_workforce_story_only_not_unrelated_incident(self):
        self.assertTrue(is_relevant(self.ARTICLE))
        self.assertFalse(is_relevant({'title_si': 'විදුහලක පාලමක් කඩා වැටේ'}))
        self.assertFalse(is_relevant({'title_si': 'මහ බැංකුව පොලී අනුපාත ඉහළ දමයි'}))

    def test_actual_classroom_path_and_archive_credit(self):
        path, credit = select_education_photo(self.ARTICLE)
        self.assertTrue(Path(path).exists())
        self.assertEqual(credit['creator'], 'Janith Dulshan')
        self.assertEqual(credit['license'], 'CC BY-SA 4.0')
        self.assertIn('පාසල් පසුබිම්', credit['label_si'])

    def test_actual_classroom_is_used_for_matching_news_reel(self):
        from real_photo import select_real_photo
        with patch('real_photo.choose_photo', return_value=None), \
             patch('institution_photo.select_institution_photo', return_value=(None,None)):
            path, kind, credit = select_real_photo(self.ARTICLE)
        self.assertEqual(kind, 'verified_education_context_photo')
        self.assertTrue(Path(path).exists())
        self.assertEqual(credit['license'], 'CC BY-SA 4.0')

    def test_telegram_post_includes_required_credit_not_extra_news_source(self):
        import os
        import fast_news
        article = dict(self.ARTICLE, published=1795354320,
                       summary_si=(self.ARTICLE['summary_si'] * 14))
        resp = MagicMock(ok=True, status_code=200)
        resp.json.return_value = {'ok': True, 'result': {'message_id': 7}}
        with patch('fast_news.publishable', return_value=True), \
             patch.dict(os.environ, {'TG_TOKEN':'dummy','TG_CHAT_ID':'dummy'}), \
             patch('requests.post', return_value=resp) as request:
            result = fast_news.send_text('telegram', article)
        self.assertEqual(result['format'], 'verified_education_context_photo')
        caption = request.call_args.kwargs['data']['caption']
        self.assertLessEqual(len(caption), 1024)
        self.assertIn('Janith Dulshan', caption)
        self.assertIn('creativecommons.org/licenses/by-sa/4.0', caption)


if __name__ == '__main__':
    unittest.main()
