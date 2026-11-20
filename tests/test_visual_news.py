import unittest
from pathlib import Path
from PIL import Image
from visual_news import original_illustration, topic_for


class OriginalNewsArtworkTests(unittest.TestCase):
    def test_topic_detection(self):
        self.assertEqual(topic_for({'title_si': 'සාමාන්‍ය පෙළ විභාග ප්‍රවේශ පත්‍ර'}), 'education')
        self.assertEqual(topic_for({'title_si': 'අද අධික වැසි සහ කාලගුණ නිවේදනය'}), 'weather')
        self.assertEqual(topic_for({'title_si': 'ක්‍රිකට් තරග ප්‍රතිඵල'}), 'sport')

    def test_generates_real_image_for_multiple_topics(self):
        for i, title in enumerate(('විභාග නිවේදනය', 'වැසි අනතුරු ඇඟවීම',
                                    'ක්‍රිකට් තරග', 'අලුත් නිවේදනය')):
            path = original_illustration({'id': 'test_art_' + str(i), 'title_si': title})
            try:
                with Image.open(path) as img:
                    self.assertEqual(img.size, (988, 752))
                    self.assertEqual(img.format, 'PNG')
            finally:
                Path(path).unlink(missing_ok=True)

    def test_empty_title_rejected(self):
        with self.assertRaises(ValueError):
            original_illustration({'title_si': ''})


if __name__ == '__main__':
    unittest.main()
