import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import requests
from PIL import Image

from subject_photos import (
    _caption_matches, _commons_photos, _download_photo, _pexels_photos,
    rule_for, subject_photo_set,
)


class SubjectPhotoTests(unittest.TestCase):
    def setUp(self):
        subject_photo_set.cache_clear()

    def test_explicit_subject_only(self):
        self.assertIsNotNone(rule_for('තරුණයින්ට වෘත්තීය පුහුණුව ලබාදීමට වැඩසටහනක්'))
        self.assertIsNotNone(rule_for('ක්‍රිකට් තරගයක්'))
        self.assertIsNone(rule_for('ක්‍රිකට් ක්‍රීඩකයෙකු අත්අඩංගුවට'))
        self.assertIsNone(rule_for('නවතම පුවත'))

    def test_current_news_topics_have_related_photo_queries(self):
        for headline in (
            '‘මිත්‍ර ශක්ති යුද අභ්‍යාසය අවසන්',
            'පෝසත්ම උදවියගේ ආදායම සියයට 6.8 කින් නැගලා',
            'ලංකාවේ ණය ශ්‍රේණිගත කිරීම් ඉහළට',
            'ග්‍රාමීය සංවර්ධන- ධීවර වැය ශීර්ෂ සම්මතයි',
            'ලෝක බෞද්ධ සංඝ සම්මේලනය හෙට ඇරැඹෙයි',
            'පාසල් නිවාඩුව දෙසැම්බර් හතර',
            'මුහුදු ප්‍රදේශවල සුළං වේගය ඉහළට',
        ):
            with self.subTest(headline=headline):
                self.assertIsNotNone(rule_for(headline))

    def test_summary_supplies_explicit_subject_for_short_headline(self):
        rule = rule_for('තවත් පිම්මකට සූදානම්',
                        'වසර 60කට පසුව පැවැත්වෙන ලෝක සංඝ සමුළුවට සූදානම්.')
        self.assertIn('Buddha statue', rule[1])
        # The headline's subject wins over unrelated secondary context.
        self.assertEqual(rule_for('කාලගුණ පුවත', 'අයවැය පිළිබඳව ද ප්‍රකාශයක්.')[1],
                         'rain clouds rainfall')

    def test_income_tax_is_not_the_income_distribution_subject(self):
        self.assertIsNone(rule_for('පින් ටින් දෙන්න ආදායම් කන්තෝරුව විවෘතයි',
                                   'ආදායම් බදු වාර්තා සඳහා PIN සහ TIN.'))

    def test_commemoration_is_not_death_or_an_unrelated_incident(self):
        self.assertIsNotNone(rule_for('බෞද්ධ සංඝ සමුළු සමරු උත්සවය'))
        self.assertIsNone(rule_for('බෞද්ධ විහාරයක අයෙක් මරුට'))
        self.assertIsNone(rule_for('පාසල් අසල අනතුරකින් තුවාල'))

    def test_caption_must_show_the_actual_country_for_named_subjects(self):
        parliament = rule_for('පාර්ලිමේන්තුවේ සැසිවාරය')
        self.assertFalse(_caption_matches('The British Parliament building', parliament))
        self.assertTrue(_caption_matches('Parliament of Sri Lanka', parliament))
        flag = rule_for('මිත්‍ර ශක්ති යුද අභ්‍යාසය')
        self.assertFalse(_caption_matches('Indian flag flying outdoors', flag))
        self.assertTrue(_caption_matches('A Sri Lankan flag in the wind', flag))
        rain = rule_for('තද වැසි')
        self.assertFalse(_caption_matches('A portrait in the rain', rain))

    def test_failed_or_empty_pexels_lookup_uses_independent_provider(self):
        photo = ('archive.jpg', 'licensed_subject_stock', {'provider': 'Wikimedia Commons'})
        with patch.dict(os.environ, {'PEXELS_API_KEY': 'test-key'}), \
             patch('subject_photos._pexels_photos', return_value=()) as pexels, \
             patch('subject_photos._commons_photos', return_value=(photo,)) as commons:
            self.assertEqual(subject_photo_set('පාසල් නිවාඩු', 'school'), (photo,))
            subject_photo_set('පාසල් නිවාඩු', 'school')
        self.assertEqual(pexels.call_count, 1)
        self.assertEqual(commons.call_count, 1)

    def test_missing_pexels_key_does_not_disable_subject_media(self):
        with patch.dict(os.environ, {'PEXELS_API_KEY': ''}), \
             patch('subject_photos._pexels_photos') as pexels, \
             patch('subject_photos._commons_photos', return_value=()) as commons:
            subject_photo_set('ලංකාවේ ණය ශ්‍රේණිගත කිරීම් ඉහළට', 'rating')
        pexels.assert_not_called()
        commons.assert_called_once()

    def test_unrecognised_story_does_not_search_arbitrary_stock(self):
        with patch('subject_photos._pexels_photos') as pexels, \
             patch('subject_photos._commons_photos') as commons:
            self.assertEqual(subject_photo_set('නවතම පුවත', 'unknown'), ())
        pexels.assert_not_called()
        commons.assert_not_called()

    def test_pexels_filters_caption_and_source_before_downloading(self):
        response = MagicMock()
        response.json.return_value = {'photos': [
            {'alt': 'A mountain', 'url': 'https://www.pexels.com/photo/1/',
             'photographer': 'A', 'src': {'large': 'https://images.pexels.com/1.jpg'}},
            {'alt': 'Coins on a table', 'url': 'https://www.pexels.com.evil/photo/2/',
             'photographer': 'B', 'src': {'large': 'https://images.pexels.com/2.jpg'}},
            {'alt': 'Coins on a table', 'url': 'https://www.pexels.com/photo/3/',
             'photographer': 'C', 'src': {'large': 'https://images.pexels.com/3.jpg'}},
        ]}
        with patch('subject_photos.requests.get', return_value=response), \
             patch('subject_photos._download_photo', return_value=('money.jpg', 'licensed_subject_stock', {})) as download:
            result = _pexels_photos(rule_for('පෝසත්ම උදවියගේ ආදායම ඉහළට'), 'income', 'test-key')
        self.assertEqual(len(result), 1)
        self.assertEqual(download.call_count, 1)
        credit = download.call_args.args[2]
        self.assertEqual(credit['provider'], 'Pexels')
        self.assertIn('Coins', credit['subject_evidence'])

    def test_pexels_timeout_is_an_empty_provider_result(self):
        with patch('subject_photos.requests.get', side_effect=requests.Timeout):
            self.assertEqual(_pexels_photos(rule_for('තද වැසි'), 'rain', 'test-key'), ())

    def test_commons_requires_relevant_subject_and_explicit_reusable_license(self):
        def page(name, license_name='CC BY 4.0', license_url='https://creativecommons.org/licenses/by/4.0/'):
            return {'title': 'File:' + name + '.jpg', 'imageinfo': [{
                'url': 'https://upload.wikimedia.org/' + name + '.jpg',
                'descriptionurl': 'https://commons.wikimedia.org/wiki/File:' + name + '.jpg',
                'extmetadata': {'Artist': {'value': 'Photographer'},
                    'LicenseShortName': {'value': license_name},
                    'LicenseUrl': {'value': license_url}}}]}
        pages = [page('British Parliament'), page('Sri Lanka Parliament', 'Copyrighted'),
                 page('Sri Lanka Parliament Archive')]
        photo = ('parliament.jpg', 'licensed_subject_stock', {})
        with patch('real_photo._metadata_search', return_value=pages), \
             patch('subject_photos._download_photo', return_value=photo) as download:
            result = _commons_photos(rule_for('පාර්ලිමේන්තුවේ සැසිවාරය'), 'parliament')
        self.assertEqual(result, (photo,))
        self.assertEqual(download.call_count, 1)
        credit = download.call_args.args[2]
        self.assertEqual(credit['provider'], 'Wikimedia Commons')
        self.assertEqual(credit['label_si'], 'Archive photo')

    def test_download_stores_licence_context_and_hash_with_image(self):
        blob = io.BytesIO()
        Image.new('RGB', (900, 600), 'grey').save(blob, format='PNG')
        response = MagicMock(status_code=200)
        response.__enter__.return_value = response
        response.iter_content.return_value = [blob.getvalue()]
        credit = {'provider': 'Pexels', 'creator': 'Photographer',
                  'license': 'Pexels License', 'license_url': 'https://www.pexels.com/license/',
                  'source': 'https://www.pexels.com/photo/1/', 'label_si': 'Stock photo'}
        previous = os.getcwd()
        try:
            with tempfile.TemporaryDirectory() as folder:
                os.chdir(folder)
                with patch('subject_photos.requests.get', return_value=response):
                    result = _download_photo('https://images.pexels.com/1.jpg', 'story', credit,
                                             'images.pexels.com')
                self.assertTrue(Path(result[0]).is_file())
                evidence = json.loads(Path(result[0] + '.credit.json').read_text())
                self.assertEqual(evidence['article_id'], 'story')
                self.assertEqual(evidence['usage'], 'subject_context_not_exact_event')
                self.assertEqual(len(evidence['sha256']), 64)
        finally:
            os.chdir(previous)

    def test_unapproved_download_host_is_never_requested(self):
        with patch('subject_photos.requests.get') as request:
            self.assertIsNone(_download_photo('https://example.com/photo.jpg', 'story', {},
                                              'images.pexels.com'))
        request.assert_not_called()


if __name__ == '__main__':
    unittest.main()

