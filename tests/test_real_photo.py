import io
import unittest
from unittest.mock import MagicMock, patch
from PIL import Image
from real_photo import permitted, select_real_photo, discover_licensed_photo


class RealPhotoTests(unittest.TestCase):
    def test_open_licenses_permitted_and_all_rights_reserved_blocked(self):
        for name in ("CC BY 4.0", "CC BY-SA 4.0", "CC0", "Public Domain"):
            info = {"extmetadata": {"LicenseShortName": {"value": name}}}
            self.assertTrue(permitted(info), name)
        self.assertFalse(permitted({"extmetadata": {"LicenseShortName": {"value": "Copyrighted"}}}))

    def test_verified_event_photo_has_priority(self):
        with patch("real_photo.choose_photo", return_value="event.jpg"), \
             patch("real_photo.discover_licensed_photo") as commons:
            photo, kind, credit = select_real_photo({"id":"one"})
            self.assertEqual((photo, kind, credit), ("event.jpg", "verified_event_photo", None))
            commons.assert_not_called()

    def test_no_exact_event_photo_never_uses_contextual_image(self):
        article = {"id": "story", "title_si": "අස්ගිරි විහාරයේ උත්සවයක්"}
        with patch("real_photo.choose_photo", return_value=None), \
             patch("real_photo.discover_licensed_photo") as fallback:
            self.assertEqual(select_real_photo(article), (None, None, None))
            fallback.assert_not_called()

    def test_approved_photo_download_error_does_not_publish_wrong_image(self):
        article = {"id": "story", "title_si": "සත්‍ය සිද්ධියක්"}
        with patch("real_photo.choose_photo", side_effect=ConnectionError("unavailable")), \
             patch("real_photo.discover_licensed_photo") as fallback:
            self.assertEqual(select_real_photo(article), (None, None, None))
            fallback.assert_not_called()

    def test_verified_bank_building_photo_selected_for_cbsl_news_only(self):
        from institution_photo import select_institution_photo, CBSL_PHOTO
        import hashlib
        import tempfile
        from pathlib import Path
        import os
        buf = io.BytesIO()
        Image.new('RGB', (772, 548), 'navy').save(buf, format='PNG')
        blob = buf.getvalue()
        client = MagicMock()
        client.get.return_value.content = blob
        with tempfile.TemporaryDirectory() as folder:
            previous = os.getcwd()
            try:
                os.chdir(folder)
                with patch.dict(CBSL_PHOTO, {'sha1': hashlib.sha1(blob).hexdigest()}), \
                     patch('institution_photo.CACHE_FILE', Path(folder) / 'not-cached.b64'):
                    path, credit = select_institution_photo(
                        {'title_si': 'මහ බැංකුව පොලී අනුපාතය වෙනස් කරයි'}, session=client)
                self.assertTrue(Path(path).exists())
                self.assertEqual(credit['creator'], 'Zsastaba')
                self.assertEqual(credit['license'], 'CC BY 4.0')
            finally:
                os.chdir(previous)
        photo, credit = select_institution_photo(
            {'title_si': 'මාතර පාලම අසල අනතුරක්'}, session=client)
        self.assertIsNone(photo)
        self.assertIsNone(credit)
        self.assertEqual(client.get.call_count, 1)

    def test_committed_real_bank_photo_matches_licensed_source_sha(self):
        import base64
        import hashlib
        from institution_photo import CACHE_FILE, CBSL_PHOTO
        self.assertTrue(CACHE_FILE.is_file())
        raw = base64.b64decode(CACHE_FILE.read_text(encoding='ascii').strip(), validate=True)
        self.assertEqual(hashlib.sha1(raw).hexdigest(), CBSL_PHOTO['sha1'])
        with Image.open(io.BytesIO(raw)) as im:
            self.assertEqual(im.size, (772, 548))

    def test_named_institution_fallback_does_not_claim_event_footage(self):
        credit = {'label_si': 'ශ්‍රී ලංකා මහ බැංකුවේ ගොඩනැගිල්ල',
                  'source': 'https://commons.wikimedia.org/wiki/File:Sri_lanka2024.png',
                  'license': 'CC BY 4.0', 'creator': 'Zsastaba',
                  'license_url': 'https://creativecommons.org/licenses/by/4.0/'}
        with patch('real_photo.choose_photo', return_value=None), \
             patch('institution_photo.select_institution_photo',
                   return_value=('bank-building.jpg', credit)):
            photo, kind, actual_credit = select_real_photo(
                {'title_si': 'ශ්‍රී ලංකා මහ බැංකුව පොලී අනුපාතය සංශෝධනය කරයි'})
        self.assertEqual((photo, kind), ('bank-building.jpg', 'verified_institution_photo'))
        self.assertEqual(actual_credit, credit)

    def test_no_license_means_no_download(self):
        session = MagicMock()
        session.get.return_value.json.return_value = {
            "query": {"pages": {"1": {"title": "File:School.jpg",
                "imageinfo": [{"width": 1000, "height": 800,
                    "url": "https://upload.wikimedia.org/example.jpg",
                    "descriptionurl": "https://commons.wikimedia.org/wiki/File:School.jpg",
                    "extmetadata": {"LicenseShortName": {"value": "copyright"}}}]}}}}
        photo, credit = discover_licensed_photo(
            {"id": "one", "title_si": "පාසල් විභාගය"}, session=session)
        self.assertIsNone(photo)
        self.assertIsNone(credit)
        self.assertEqual(session.get.call_count, 2)


if __name__ == "__main__":
    unittest.main()
