import copy
import os
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
import fast_news as pipeline

class NewsTests(unittest.TestCase):
    def test_native_freshness_and_broken_xml(self):
        now = time.time()
        fresh = datetime.fromtimestamp(now - 60, timezone.utc).isoformat()
        xml = f'''<rss><channel><item><title>ශ්‍රී ලංකාවේ අලුත් පුවතක්</title><link>https://example.com/a</link><pubDate>{fresh}</pubDate><description>පුවත් සාරාංශයකි</description></item><item><title>පැරණි පුවතක්</title><link>https://example.com/old</link><pubDate>Mon, 01 Jan 2024 10:00:00 GMT</pubDate></item><item><title>Undated story</title><link>https://example.com/undated</link></item></channel></rss>'''
        stories, total = pipeline.parse_feed(xml.encode(), 'Test', now)
        self.assertEqual(total, 3)
        self.assertEqual(len(stories), 1)
        self.assertEqual(stories[0]['link'], 'https://example.com/a')
        self.assertEqual(pipeline.fingerprint('ශ්‍රී ලංකා!'), pipeline.fingerprint('ශ්‍රී ලංකා'))

    def test_receipts_and_partial_failure(self):
        story = {'id':'one', 'published':time.time(), 'title_si':'පුවත', 'summary_si':'', 'source':'Test','link':'https://example.com'}
        state = {}
        calls = []
        def sender(name, article):
            calls.append(name)
            if name == 'facebook' and calls.count(name) == 1:
                return {'error':'api_rejected'}
            return {'id':'123'}
        with tempfile.TemporaryDirectory() as directory, patch.object(pipeline, 'STATE_FILE', Path(directory)/'state.json'):
            result, _ = pipeline.deliver(state, [story], time.time(), sender=sender)
            self.assertEqual(result['facebook']['failed'], 1)
            pipeline.deliver(state, [story], time.time(), sender=sender)
            self.assertEqual(calls, ['telegram','facebook','facebook'])
            saved = Path(directory, 'state.json').read_text()
            pipeline.deliver(state, [dict(story, id='two')], time.time(), preview=True, sender=sender)
            self.assertEqual(Path(directory, 'state.json').read_text(), saved)
            self.assertEqual(len(calls),3)

    def test_lost_response_does_not_repeat_or_block_new_story(self):
        story = {'id':'one','published':time.time(),'title_si':'පුවත','summary_si':'','source':'Test','link':'https://example.com'}
        state = {}
        calls = []
        def sender(name, article):
            calls.append((name,article['id']))
            raise TimeoutError()
        with tempfile.TemporaryDirectory() as directory, patch.object(pipeline, 'STATE_FILE', Path(directory)/'state.json'):
            pipeline.deliver(state, [story], time.time(), sender=sender)
            pipeline.deliver(state, [story, dict(story,id='two')], time.time(), sender=sender)
        self.assertEqual(calls, [('telegram','one'),('facebook','one'),('telegram','two'),('facebook','two')])

if __name__ == '__main__':
    unittest.main()
