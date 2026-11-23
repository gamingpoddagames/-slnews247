import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from footage_discovery import discover_pexels_media

class PexelsConnectorTests(unittest.TestCase):
    def test_missing_key_does_not_request_media(self):
        with patch.dict(os.environ, {'PEXELS_API_KEY': ''}):
            result = discover_pexels_media([], fetcher=lambda *a, **k: self.fail('No key'))
        self.assertEqual(result['status'], 'missing_api_key')

    def test_results_remain_unapproved_and_key_is_not_in_report(self):
        def fetch(url, **kwargs):
            self.assertEqual(kwargs['headers']['Authorization'], 'test-private-key')
            payload = {'photos': [{'url': 'https://www.pexels.com/photo/1', 'photographer': 'Creator', 'src': {'original': 'https://images.pexels.com/1.jpg'}}]} if url.endswith('/search') and '/videos/' not in url else {'videos': []}
            return SimpleNamespace(status_code=200, raise_for_status=lambda: None, json=lambda: payload)
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'PEXELS_API_KEY': 'test-private-key'}):
            path = str(Path(folder) / 'result.json')
            result = discover_pexels_media([{'id': 'a', 'link': 'https://news.example/a', 'title_si': 'news'}], output_path=path, fetcher=fetch)
            text = Path(path).read_text()
            entry = json.loads(text)[0]
        self.assertEqual(result['status'], 'checked')
        self.assertFalse(entry['may_download_or_publish'])
        self.assertFalse(entry['verified_event'])
        self.assertNotIn('test-private-key', text)
