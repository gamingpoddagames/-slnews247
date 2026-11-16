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

class PresentationTests(unittest.TestCase):
    def test_caption_has_no_visible_source_or_url(self):
        article = {'title_si':'ශ්‍රී ලංකා පුවත්', 'summary_si':'පුවත් කෙටියෙන්',
                   'source':'Publisher', 'link':'https://example.com/story', 'published':time.time()}
        text = pipeline.caption(article)
        self.assertNotIn('Publisher', text)
        self.assertNotIn('https://', text)
        self.assertNotIn('මූලාශ්‍රය', text)
        self.assertIn('SL News 247', text)

    def test_photo_license_and_topic_selection(self):
        from media import CATALOG, LICENSE, topic
        self.assertEqual(topic({'title_si':'කාලගුණ නිවේදනයක්'}), 'weather')
        self.assertEqual(topic({'title_si':'දුම්රිය ප්‍රවාහන සේවය'}), 'transport')
        self.assertEqual(topic({'title_si':'බැංකු ආර්ථික පුවත්'}), 'business')
        self.assertEqual(LICENSE, 'https://www.pexels.com/license/')
        self.assertTrue(all(a['page'].startswith('https://www.pexels.com/photo/') for a in CATALOG.values()))

    def test_photo_post_request_uses_uploaded_image(self):
        from unittest.mock import MagicMock
        article = {'id':'one', 'title_si':'පුවත', 'summary_si':'', 'published':time.time()}
        response = MagicMock()
        response.ok = True
        response.json.return_value = {'ok':True,'result':{'message_id':99}}
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory, 'test.jpg');image.write_bytes(b'image-fixture')
            with patch('media.post_image', return_value=str(image)), patch.dict(os.environ, {'TG_TOKEN':'test','TG_CHAT_ID':'test'}), patch('requests.post', return_value=response) as request:
                result = pipeline.send_text('telegram', article)
                self.assertEqual(result['format'], 'photo')
                self.assertTrue(request.call_args.args[0].endswith('/sendPhoto'))
                self.assertIn('photo', request.call_args.kwargs['files'])
                self.assertNotIn('https://', request.call_args.kwargs['data']['caption'])
