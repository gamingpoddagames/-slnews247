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
