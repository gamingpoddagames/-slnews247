import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from footage_discovery import discover_article_photos

class PhotoCandidatesTests(unittest.TestCase):
    def test_preview_image_is_only_a_review_lead(self):
        article = {'id': 'story', 'title_si': 'පුවත', 'link': 'https://siyathanews.lk/archives/1'}
        calls = []
        def fetch(url, **kwargs):
            calls.append(url)
            return SimpleNamespace(url=url, content=b'<meta property="og:image" content="/event.jpg">', raise_for_status=lambda: None)
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder) / 'photos.json')
            report = discover_article_photos([article], output_path=path, fetcher=fetch)
            entry = json.loads(Path(path).read_text())[0]
        self.assertEqual(report['examined'], 1)
        self.assertEqual(calls, [article['link']])
        self.assertEqual(entry['image_url'], 'https://siyathanews.lk/event.jpg')
        self.assertFalse(entry['may_download_or_publish'])
        self.assertEqual(entry['status'], 'event_and_rights_verification_required')

    def test_unknown_publisher_is_not_requested(self):
        def fetch(*args, **kwargs):
            self.fail('Unsupported publisher requested')
        with tempfile.TemporaryDirectory() as folder:
            report = discover_article_photos([{'link': 'https://unknown.example/post'}], output_path=str(Path(folder)/'photos.json'), fetcher=fetch)
        self.assertEqual(report['examined'], 0)
