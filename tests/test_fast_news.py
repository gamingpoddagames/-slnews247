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


    def test_unlicensed_story_still_gets_original_brand_card(self):
        from unittest.mock import MagicMock
        article = {'id':'new', 'title_si':'නවතම පුවතක්', 'summary_si':'සාරාංශය',
                   'published':time.time(), 'link':'https://example.com/a'}
        response = MagicMock()
        response.ok = True
        response.json.return_value = {'ok':True,'result':{'message_id':101}}
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory, 'card.png')
            image.write_bytes(b'graphic-test')
            with patch('media.post_image', return_value=None), patch('image.news_card', return_value=str(image)) as card, patch.dict(os.environ, {'TG_TOKEN':'test', 'TG_CHAT_ID':'test'}), patch('requests.post', return_value=response) as request:
                result = pipeline.send_text('telegram', article)
                self.assertEqual(result['format'], 'photo')
                card.assert_called_once_with(article)
                self.assertTrue(request.call_args.args[0].endswith('/sendPhoto'))

class ExactEventMediaTests(unittest.TestCase):
    def test_no_event_photo_uses_branded_card_and_skips_video(self):
        from unittest.mock import MagicMock
        article = {'id':'new','title_si':'පුවත','summary_si':'','published':time.time(),'link':'https://example.com/a'}
        response = MagicMock();response.ok=True
        response.json.return_value={'ok':True,'result':{'message_id':100}}
        with tempfile.TemporaryDirectory() as directory:
            card_path = Path(directory, 'news.png')
            card_path.write_bytes(b'original-typography-card')
            with patch('media.post_image', return_value=None), patch('image.news_card', return_value=str(card_path)), patch.dict(os.environ, {'TG_TOKEN':'test','TG_CHAT_ID':'test'}), patch('requests.post', return_value=response) as request:
                result=pipeline.send_text('telegram', article)
                self.assertEqual(result['format'],'photo')
                self.assertTrue(request.call_args.args[0].endswith('/sendPhoto'))
                self.assertIn('files',request.call_args.kwargs)
        with patch('media.choose_video', return_value=None):
            self.assertEqual(pipeline.maybe_video({},[article],time.time(),False),'skipped_no_verified_event_video_or_official_link')

    def test_exact_story_and_nonreuse_guards(self):
        import hashlib, io, json
        import media
        from PIL import Image
        from unittest.mock import MagicMock
        stream=io.BytesIO();Image.new('RGB',(800,800),'blue').save(stream,format='JPEG')
        blob=stream.getvalue();digest=hashlib.sha256(blob).hexdigest()
        a={'id':'one','link':'https://example.com/one'}
        b={'id':'two','link':'https://example.com/two'}
        asset={'article_url':a['link'],'verified_event':True,'rights_verified':True,
               'attribution_required':False,'verification_notes':'Exact event reviewed',
               'rights_evidence':'Owner permission recorded','sha256':digest,'url':'https://example.com/media.jpg'}
        response=MagicMock();response.content=blob
        old=os.getcwd()
        with tempfile.TemporaryDirectory() as directory:
            try:
                os.chdir(directory)
                registry=Path('registry.json');usage=Path('usage.json')
                with patch.object(media,'REGISTRY',registry),patch.object(media,'USAGE',usage),patch('requests.get',return_value=response) as request:
                    self.assertIsNone(media.choose_photo(a))
                    request.assert_not_called()
                    registry.write_text(json.dumps({'one':dict(asset,article_url='wrong')}))
                    self.assertIsNone(media.choose_photo(a))
                    registry.write_text(json.dumps({'one':asset,'two':dict(asset,article_url=b['link'])}))
                    self.assertIsNotNone(media.choose_photo(a))
                    self.assertIsNotNone(media.choose_photo(a))
                    self.assertIsNone(media.choose_photo(b))
                    registry.write_text(json.dumps({'one':dict(asset,rights_verified=False)}))
                    self.assertIsNone(media.choose_photo(a))
            finally:
                os.chdir(old)

class GenuineVideoTests(unittest.TestCase):
    def test_photo_and_unverified_video_cannot_enter_video_branch(self):
        import json, media
        article={'id':'one','link':'https://example.com/story'}
        asset={'article_url':article['link'],'verified_event':True,'rights_verified':True,
               'attribution_required':False,'verification_notes':'Reviewed story',
               'rights_evidence':'Permission on file','sha256':'test','url':'https://example.com/clip.mp4'}
        with tempfile.TemporaryDirectory() as directory:
            registry=Path(directory,'registry.json')
            with patch.object(media,'REGISTRY',registry),patch('requests.get') as download:
                registry.write_text(json.dumps({'one':asset}))
                self.assertIsNone(media.choose_video(article))
                registry.write_text(json.dumps({'one':{'video':asset}}))
                self.assertIsNone(media.choose_video(article))
                download.assert_not_called()

class EditorialTests(unittest.TestCase):
    def test_exact_article_review_and_official_video_guards(self):
        import editorial,json
        article={'id':'a','link':'https://example.com/story'}
        brief={'article_url':article['link'],'facts_reviewed':True,'source_refs':['https://example.com/source'],
               'body_si':'කරුණු තහවුරු කළ අපගේම පුවත් සාරාංශයකි.',
               'official_video_url':'https://www.youtube.com/watch?v=test',
               'official_video_verified':True,'official_video_evidence':'Article embeds exact official event clip'}
        with tempfile.TemporaryDirectory() as directory:
            file=Path(directory,'briefs.json')
            with patch.object(editorial,'BRIEFS',file):
                file.write_text(json.dumps({'a':brief}))
                self.assertEqual(editorial.brief_for(article)['body_si'],brief['body_si'])
                self.assertEqual(editorial.official_video_for(article),brief['official_video_url'])
                self.assertEqual(editorial.brief_for(dict(article,link='wrong')), {})
                file.write_text(json.dumps({'a':dict(brief,official_video_verified=False)}))
                self.assertIsNone(editorial.official_video_for(article))

class EditorialDeliveryTests(unittest.TestCase):
    def test_original_brief_is_shared_once_without_resending_headline(self):
        article={'id':'a','title_si':'පුවත','summary_si':'කෙටි පුවත','published':time.time(),'link':'https://example.com/a'}
        state={}
        with patch('editorial.brief_for',return_value={'body_si':'අපේම වචනවලින් ලියූ විස්තරාත්මක සාරාංශය.'}),patch.object(pipeline,'save'),patch.object(pipeline,'send_text',return_value={'id':'10'}) as send:
            pipeline.share_editorial_update(state,[article],time.time(),False)
            pipeline.share_editorial_update(state,[article],time.time(),False)
            self.assertEqual(send.call_count,2)
            self.assertTrue(send.call_args.args[1]['title_si'].startswith('විස්තරාත්මක පුවත'))

class PublisherPlayerTests(unittest.TestCase):
    def test_only_single_exact_article_player_is_selected(self):
        from publisher_videos import extract_video,youtube_watch
        clip='https://www.youtube.com/embed/X5LpOsYyDiU?feature=oembed'
        self.assertEqual(youtube_watch(clip),'https://www.youtube.com/watch?v=X5LpOsYyDiU')
        self.assertIsNone(extract_video('<footer><iframe src="'+clip+'"></iframe></footer>'))
        self.assertEqual(extract_video('<div class="td-post-content"><iframe src="'+clip+'"></iframe></div>'),'https://www.youtube.com/watch?v=X5LpOsYyDiU')
        self.assertIsNone(extract_video('<div class="entry-content"><iframe src="'+clip+'"></iframe><iframe src="https://youtube.com/embed/x3CE2K5CwT8"></iframe></div>'))
        self.assertIsNone(youtube_watch('https://youtube.com/embed/live_stream?channel=wrong'))
