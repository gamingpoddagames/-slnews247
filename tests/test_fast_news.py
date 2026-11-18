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
        story = {'id':'one', 'published':time.time(), 'title_si':'මාතර සිද්ධිය', 'summary_si':'මාතර සිද්ධිය සම්බන්ධයෙන් මේ වනවිට පොලිසිය විමර්ශන ආරම්භ කර තිබේ.', 'source':'Test','link':'https://example.com'}
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
        story = {'id':'one','published':time.time(),'title_si':'මාතර සිද්ධිය','summary_si':'මාතර සිද්ධිය සම්බන්ධයෙන් මේ වනවිට පොලිසිය විමර්ශන ආරම්භ කර තිබේ.','source':'Test','link':'https://example.com'}
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
        self.assertIn('SL NEWS 24/7', text)

    def test_photo_post_request_uses_uploaded_image(self):
        from unittest.mock import MagicMock
        article = {'id':'one', 'title_si':'මාතර සිද්ධිය', 'summary_si':'මාතර සිද්ධිය සම්බන්ධයෙන් මේ වනවිට පොලිසිය විමර්ශන ආරම්භ කර තිබේ.', 'published':time.time()}
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
        article = {'id':'new', 'title_si':'මාතර සිද්ධිය', 'summary_si':'මාතර සිද්ධිය සම්බන්ධයෙන් මේ වනවිට පොලිසිය විමර්ශන ආරම්භ කර තිබේ.',
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
        article = {'id':'new','title_si':'මාතර සිද්ධිය','summary_si':'මාතර සිද්ධිය සම්බන්ධයෙන් මේ වනවිට පොලිසිය විමර්ශන ආරම්භ කර තිබේ.','published':time.time(),'link':'https://example.com/a'}
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
            self.assertEqual(pipeline.maybe_video({},[article],time.time(),False),'no_renderable_news_bulletin_candidate')

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


class MixedScriptCardTests(unittest.TestCase):
    def test_english_words_are_preserved_in_sinhala_titles(self):
        from image import script_runs
        title = 'LAUGFS ගෑස් 12.5kg Rs. 5,995'
        self.assertEqual(''.join(script_runs(title)), title)
        self.assertIn('LAUGFS', ''.join(script_runs(title)))
        self.assertIn('ගෑස්', ''.join(script_runs(title)))

    def test_mixed_script_card_can_render_without_missing_glyph_substitution(self):
        from PIL import Image, ImageDraw
        from image import mixed_width, draw_mixed
        canvas = Image.new('RGB', (1200, 200), 'black')
        draw = ImageDraw.Draw(canvas)
        title = 'LAUGFS ගෑස් 12.5kg මිල අඩු කරයි'
        self.assertGreater(mixed_width(draw, title, 45), 200)
        self.assertGreater(draw_mixed(draw, (20, 100), title, 45), 200)
        self.assertIsNotNone(canvas.getbbox())



class CompleteStoryTests(unittest.TestCase):
    def test_clipped_excerpt_never_shows_dangling_fragment(self):
        raw = ('මාතර ප්‍රදේශයේ නිවසක් තුළදී පුද්ගලයෙකු ඝාතනය කර තිබේ. '
               'මියගිය පුද්ගලයා වයස අවුරුදු 39ක අයෙකි. අදාළ…')
        self.assertEqual(pipeline.complete_sentences(raw),
                         'මාතර ප්‍රදේශයේ නිවසක් තුළදී පුද්ගලයෙකු ඝාතනය කර තිබේ. '
                         'මියගිය පුද්ගලයා වයස අවුරුදු 39ක අයෙකි.')
        self.assertNotIn('…', pipeline.complete_sentences(raw))

    def test_rss_summary_preserves_full_complete_sentences(self):
        now = time.time()
        pub = datetime.fromtimestamp(now-30, timezone.utc).strftime('%a, %d %b %Y %H:%M:%S GMT')
        summary = ('පළමු වැදගත් වාක්‍යය සම්පූර්ණයි. ' +
                   'දෙවන වාක්‍යයේ සවිස්තරාත්මක කරුණු ' * 12 + 'අවසන් වේ. '
                   'තවත් අසම්පූර්ණ')
        xml = f'<rss><channel><item><title>දෙවන වාක්‍යයේ සවිස්තරාත්මක කරුණු පිළිබඳ පුවතක්</title><link>https://example.com/1</link><pubDate>{pub}</pubDate><description>{summary}</description></item></channel></rss>'
        stories, _ = pipeline.parse_feed(xml.encode(), 'Test', now)
        self.assertEqual(stories[0]['summary_si'], pipeline.complete_sentences(summary))
        self.assertTrue(stories[0]['summary_si'].endswith('අවසන් වේ.'))
        self.assertGreater(len(stories[0]['summary_si']), 200)

    def test_caption_omits_partial_sentence(self):
        story={'title_si':'මාතර ප්‍රදේශයේ මනුෂ්‍ය ඝාතනයක්',
               'summary_si':'පළමු වාක්‍යය සම්පූර්ණයි. අදාළ…',
               'published':time.time()}
        caption=pipeline.caption(story)
        self.assertIn('පළමු වාක්‍යය සම්පූර්ණයි.', caption)
        self.assertNotIn('අදාළ…', caption)



class QualityGateTests(unittest.TestCase):
    def test_mismatched_sports_and_veterinary_description_is_rejected(self):
        title = 'ශ්‍රී ලංකා පාපන්දු කණ්ඩායමේ නායක සුජාන් පෙරේරා සමුදෙයි'
        wrong = 'පශු වෛද්‍ය නිලධාරීන්ගේ සංගමය අද වෘත්තීය සමිති ක්‍රියාමාර්ගයක නිරත වීමට තීරණය කර තිබේ.'
        self.assertFalse(pipeline.relevant_summary(title, wrong))
        self.assertFalse(pipeline.publishable({'title_si':title,'summary_si':wrong}))

    def test_complete_matching_body_is_publishable(self):
        story = {'title_si':'මාතර ප්‍රදේශයේ ඝාතනයක්',
                 'summary_si':'මාතර ප්‍රදේශයේ නිවසක් තුළදී පුද්ගලයෙකු ඝාතනය කර ඇති අතර පොලිසිය විමර්ශන ආරම්භ කර තිබේ.'}
        self.assertTrue(pipeline.publishable(story))

    def test_empty_story_is_not_sent_or_checkpointed(self):
        article = {'id':'empty', 'title_si':'පාපන්දු ක්‍රීඩා පුවතක්',
                   'summary_si':'', 'published':time.time()}
        with patch.object(pipeline, 'save'), patch.object(pipeline, 'send_text') as send:
            result, selected = pipeline.deliver({}, [article], time.time())
        self.assertEqual(selected, [])
        self.assertEqual(result['facebook']['sent'], 0)
        send.assert_not_called()



class ReviewedFootageEditsTests(unittest.TestCase):
    def test_ads_require_review_and_valid_intervals(self):
        from unittest.mock import patch
        from video import trim_reviewed_ad_segments
        with patch('video.probe_footage', return_value={'duration':40, 'has_audio':True}):
            with self.assertRaises(ValueError):
                trim_reviewed_ad_segments('in.mp4','out.mp4',[[4,9]],reviewed=False)
            with self.assertRaises(ValueError):
                trim_reviewed_ad_segments('in.mp4','out.mp4',[[10,5]],reviewed=True)
            with self.assertRaises(ValueError):
                trim_reviewed_ad_segments('in.mp4','out.mp4',[[3,14],[12,21]],reviewed=True)
            with patch('video.subprocess.run') as run:
                path=trim_reviewed_ad_segments('in.mp4','out.mp4',[[3,8],[28,33]],reviewed=True)
                self.assertEqual(path,'out.mp4')
                cmd=run.call_args.args[0]
                self.assertIn('-an',cmd)
                self.assertIn('concat=n=3:v=1:a=0[out]',cmd[cmd.index('-filter_complex')+1])



class AutomaticAdCandidateTests(unittest.TestCase):
    def test_black_and_silent_transition_flags_intro_only_for_review(self):
        from ad_detector import candidate_intervals
        candidates = candidate_intervals(120, [(10, 10.5)], [(10, 11)])
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]['status'], 'review_required')
        self.assertEqual((candidates[0]['start'], candidates[0]['end']), (0.0, 10.25))

    def test_no_silence_or_midclip_transition_does_not_infer_ad(self):
        from ad_detector import candidate_intervals
        self.assertEqual(candidate_intervals(120, [(10, 10.5)], []), [])
        self.assertEqual(candidate_intervals(120, [(60, 60.5)], [(60,61)]), [])

    def test_detector_report_never_deletes_footage(self):
        from unittest.mock import MagicMock
        from ad_detector import detect_ad_candidates
        stderr = ('black_start:10 black_end:10.5 black_duration:0.5\n'
                  '[silencedetect] silence_start: 10\n'
                  '[silencedetect] silence_end: 11 | silence_duration: 1')
        process=MagicMock(returncode=0,stderr=stderr)
        with tempfile.TemporaryDirectory() as directory,patch('video.probe_footage',return_value={'duration':120}),patch('ad_detector.subprocess.run',return_value=process):
            result=detect_ad_candidates('video.mp4', str(Path(directory)/'review.json'))
            self.assertFalse(result['automatic_cut'])
            self.assertFalse(result['source_watermark_modified'])
            self.assertTrue(result['candidates'])


class MultiPublisherCoverageTests(unittest.TestCase):
    def test_multiple_independent_sinhala_publishers_and_sections(self):
        sources = pipeline.SOURCES
        self.assertGreaterEqual(len(sources), 20)
        hosts = {__import__('urllib.parse', fromlist=['urlparse']).urlparse(u).hostname for _, u in sources}
        self.assertTrue(any('adaderana' in (h or '') for h in hosts))
        self.assertTrue(any('siyathanews' in (h or '') for h in hosts))
        self.assertTrue(any('lankadeepa' in (h or '') for h in hosts))
        self.assertTrue(any('nethnews' in (h or '') for h in hosts))
        self.assertEqual(len({u for _,u in sources}),len(sources))

    def test_batch_accepts_more_than_ten_valid_stories(self):
        now = time.time()
        stories = [
            {'id':str(i), 'published':now, 'title_si':f'මාතර සිද්ධිය {i}',
             'summary_si':'මාතර සිද්ධිය සම්බන්ධයෙන් පොලිසිය වැඩිදුර විමර්ශන සිදුකරමින් සිටින බව වාර්තා වෙයි.'}
            for i in range(15)
        ]
        with patch.object(pipeline, 'save'), patch.dict(os.environ, {'MAX_NEWS_PER_RUN':'30'}):
            result, selected = pipeline.deliver({}, stories, now, preview=True)
        self.assertEqual(len(selected),15)
        self.assertEqual(result['facebook']['sent'],0)



class NewsCardTextBoundsTests(unittest.TestCase):
    def test_long_sinhala_headline_stays_inside_card(self):
        from PIL import Image, ImageDraw
        from image import fit_headline, mixed_width
        draw = ImageDraw.Draw(Image.new('RGB', (1080, 1080)))
        title = 'ශ්‍රී ලංකාවේ දිස්ත්‍රික්ක ගණනාවකට බලපාන අයහපත් කාලගුණික තත්ත්වය පිළිබඳ නවතම නිවේදනය සහ අදාළ ප්‍රදේශවලට දැනුම්දීමක්'
        size, lines, step = fit_headline(draw, title)
        self.assertEqual(' '.join(lines), title)
        self.assertTrue(all(mixed_width(draw, line, size) <= 950 for line in lines))
        self.assertLessEqual(len(lines) * step, 550)

    def test_oversized_unbroken_word_is_rejected_not_clipped(self):
        from PIL import Image, ImageDraw
        from image import fit_headline
        draw = ImageDraw.Draw(Image.new('RGB', (1080, 1080)))
        with self.assertRaises(ValueError):
            fit_headline(draw, 'EXTRALONGUNBROKEN' * 100)


    def test_published_news_card_has_no_details_below_banner(self):
        from PIL import Image
        from image import news_card
        story = {'id': 'caption-above-test',
                 'title_si': 'අම්බලන්ගොඩ ප්‍රදේශයේ මත්ද්‍රව්‍ය වැටලීමක්'}
        with tempfile.TemporaryDirectory() as root:
            previous = os.getcwd()
            try:
                os.chdir(root)
                path = news_card(story)
                with Image.open(path) as img:
                    # This used to be a bright yellow "details below" banner.
                    self.assertEqual(img.getpixel((540, 1250)), (32, 33, 36))
            finally:
                os.chdir(previous)

    def test_actual_branded_card_is_saved_at_correct_size(self):
        from PIL import Image
        from image import news_card
        story = {'id': 'bounds-test', 'title_si': 'අම්බලන්ගොඩ ප්‍රදේශයේ වැටලීමකින් විශේෂ හෙළිදරව්වක් සිදු වී තිබෙන බව පොලිසිය පවසයි'}
        with tempfile.TemporaryDirectory() as root:
            previous = os.getcwd()
            try:
                os.chdir(root)
                path = news_card(story)
                with Image.open(path) as rendered:
                    self.assertEqual(rendered.size, (1080, 1350))
            finally:
                os.chdir(previous)


class SinhalaGlyphRegressionTests(unittest.TestCase):
    def test_unicode_range_splits_true_sinhala_from_english(self):
        from image import script_runs, _sinhala_char
        self.assertEqual(script_runs('SL NEWS ගෑස් 24/7'), ['SL NEWS ', 'ගෑස්', ' 24/7'])
        self.assertTrue(_sinhala_char('ග'))
        self.assertFalse(_sinhala_char('S'))
        self.assertTrue(_sinhala_char('\u200D'))

    def test_renderer_uses_noto_for_sinhala_and_latin_for_english(self):
        from PIL import Image, ImageDraw
        from image import draw_mixed, mixed_width
        from unittest.mock import patch
        canvas = Image.new('RGB', (900, 180), 'black')
        draw = ImageDraw.Draw(canvas)
        with patch('image.get_font', wraps=__import__('image').get_font) as sino, \
             patch('image.latin_font', wraps=__import__('image').latin_font) as latin:
            draw_mixed(draw, (10, 100), 'SL NEWS ගෑස් 24/7', 42)
            self.assertTrue(sino.called)
            self.assertTrue(latin.called)
        self.assertGreater(mixed_width(draw, 'ගෑස්', 42), 10)
        self.assertIsNotNone(canvas.getbbox())

    def test_correct_sinhala_font_is_not_latin_missing_glyph(self):
        from PIL import ImageFont
        from image import get_font, latin_font
        sinhala = get_font(45)
        latin = latin_font(45)
        self.assertNotEqual(sinhala.path, latin.path)
        self.assertIsNotNone(sinhala.getmask('සිංහල').getbbox())

class PhotoFirstPosterTests(unittest.TestCase):

    def test_blank_photo_area_is_seamless_shaded_navy_no_shapes(self):
        from PIL import Image
        from image import news_card
        story={'id':'seamless-blue','title_si':'ශ්‍රී ලංකාවේ නව පුවතක්',
               'published':1794921000}
        with tempfile.TemporaryDirectory() as root:
            previous=os.getcwd()
            try:
                os.chdir(root)
                with Image.open(news_card(story)) as img:
                    center=img.getpixel((540,430))
                    edge=img.getpixel((110,430))
                    # Subtle royal-blue center and navy edges; no icon or box.
                    self.assertGreater(center[2], center[0] * 4)
                    self.assertGreater(center[2], edge[2] + 40)
                    # Close neighbors should never create a geometric outline.
                    for x,y in ((280,320),(540,430),(760,500),(450,600)):
                        a=img.getpixel((x,y))
                        b=img.getpixel((x+2,y+2))
                        self.assertLessEqual(max(abs(u-v) for u,v in zip(a,b)), 7)
                    self.assertGreater(img.getpixel((12,155))[0],img.getpixel((12,155))[2])
                    self.assertGreater(img.getpixel((12,1190))[2],img.getpixel((12,1190))[0])
            finally:
                os.chdir(previous)

    def test_no_photo_has_blue_area_and_split_color_frame(self):
        from PIL import Image
        from image import news_card
        story={'id':'blue-fallback','title_si':'මාතර ප්‍රදේශයේ නව පුවතක්','published':1794921000}
        with tempfile.TemporaryDirectory() as root:
            previous=os.getcwd()
            try:
                os.chdir(root)
                with Image.open(news_card(story)) as img:
                    top=img.getpixel((10,150))
                    bottom=img.getpixel((10,1200))
                    blue=img.getpixel((500,170))
                    self.assertGreater(top[0], top[2])  # orange-red border
                    self.assertGreater(bottom[2], bottom[0])  # blue border
                    self.assertGreater(blue[2], blue[0])  # blue photo fallback
                    self.assertEqual(img.size,(1080,1350))
            finally:
                os.chdir(previous)

    def test_photo_overrides_blue_fallback_without_changing_frame(self):
        from PIL import Image
        from image import news_card
        story={'id':'with-photo','title_si':'මාතර ප්‍රදේශයේ නව පුවතක්','published':1794921000}
        with tempfile.TemporaryDirectory() as root:
            previous=os.getcwd()
            try:
                os.chdir(root)
                Image.new('RGB',(1000,800),(218,43,37)).save('event.png')
                with Image.open(news_card(story,image_path='event.png')) as img:
                    self.assertEqual(img.getpixel((500,350)),(218,43,37))
                    self.assertGreater(img.getpixel((10,1200))[2],img.getpixel((10,1200))[0])
            finally:
                os.chdir(previous)

    def test_verified_photo_is_rendered_with_poster_layout(self):
        from PIL import Image
        from image import news_card
        story={'id':'photo-test','title_si':'ගම්පහ ප්‍රදේශයේ විශේෂ වැඩසටහනක් පැවැත්වේ',
               'published':1794921000}
        with tempfile.TemporaryDirectory() as root:
            previous=os.getcwd()
            try:
                os.chdir(root)
                Image.new('RGB',(900,700),(12,210,32)).save('photo.jpg')
                path=news_card(story,image_path='photo.jpg')
                with Image.open(path) as img:
                    self.assertEqual(img.size,(1080,1350))
                    self.assertTrue(all(abs(a-b) <= 3 for a,b in zip(img.getpixel((500,400)), (12,210,32))))
                    self.assertEqual(img.getpixel((500,1250)),(32,33,36))
            finally:
                os.chdir(previous)

    def test_unverified_photo_is_not_passed_to_poster(self):
        import media
        article={'id':'unverified','title_si':'මාතර පුවතක්'}
        with patch('media.choose_photo',return_value=None),patch('image.news_card') as draw:
            self.assertIsNone(media.post_image(article))
            draw.assert_not_called()


class NewsCheckpointMergeTests(unittest.TestCase):
    def test_merge_preserves_remote_receipts_and_adds_local(self):
        from scripts.merge_news_checkpoint import merge_state
        remote={'last_scan_at':100, 'stories':{'same':{'article':{'id':'same'},'receipts':{'telegram':{'id':'90'}},'uncertain':{'facebook':True}}}}
        local={'last_scan_at':110, 'stories':{'same':{'article':{'id':'same'},'receipts':{'facebook':{'id':'post-1'}},'uncertain':{}},'new':{'article':{'id':'new'},'receipts':{}}}}
        result=merge_state(remote,local)
        self.assertEqual(result['last_scan_at'],110)
        self.assertEqual(result['stories']['same']['receipts']['telegram']['id'],'90')
        self.assertEqual(result['stories']['same']['receipts']['facebook']['id'],'post-1')
        self.assertNotIn('facebook',result['stories']['same']['uncertain'])
        self.assertIn('new',result['stories'])


class IllustrativePhotoSafetyTests(unittest.TestCase):
    def test_cc0_photo_is_labelled_and_not_claimed_as_event(self):
        from PIL import Image
        from media import post_image
        article={'id':'expressway-test','title_si':'රුවන්පුර අධිවේගී මාර්ගය සඳහා කැබිනට් අනුමැතිය',
                 'published':1794921000,'illustrative_photo':'sri_lanka_expressway_cc0'}
        def mock_download(url,path):
            Image.new('RGB',(900,700),(42,91,142)).save(path)
            return True
        with tempfile.TemporaryDirectory() as root:
            previous=os.getcwd()
            try:
                os.chdir(root)
                with patch('media.choose_photo',return_value=None),patch('image.download_image',side_effect=mock_download):
                    path=post_image(article)
                with Image.open(path) as img:
                    self.assertEqual(img.size,(1080,1350))
                    self.assertTrue(all(abs(a-b) <= 3 for a,b in zip(img.getpixel((500,350)),(42,91,142))))
            finally:
                os.chdir(previous)
        self.assertIn('සංකේතාත්මක ඡායාරූපයක්',pipeline.caption(article))
        self.assertIn('CC0',pipeline.caption(article))

    def test_unapproved_illustration_cannot_download(self):
        from media import post_image
        article={'id':'bad-image','title_si':'මාතර පුවතක්',
                 'illustrative_photo':'https://untrusted.invalid/a.jpg'}
        with patch('media.choose_photo',return_value=None),patch('image.download_image') as download:
            self.assertIsNone(post_image(article))
            download.assert_not_called()


class VideoSystemRecoveryTests(unittest.TestCase):

    def test_skips_unnarratable_story_and_uses_next_delivered_story(self):
        now=time.time()
        bad={'id':'bad','title_si':'මාතර පුවතක්','summary_si':'', 'published':now}
        good={'id':'good','title_si':'මාතර ප්‍රදේශයේ විශේෂ සිද්ධියක්',
              'summary_si':'මාතර ප්‍රදේශයේ විශේෂ සිද්ධියක් සම්බන්ධයෙන් පොලිසිය විමර්ශන ආරම්භ කර තිබේ.',
              'published':now}
        state={'stories':{'bad':{'receipts':{'telegram':{},'facebook':{}}},
                         'good':{'receipts':{'telegram':{},'facebook':{}}}}}
        with patch('animated_bulletin.render_bulletin',return_value='demo.mp4'), \
             patch.object(pipeline,'save'), \
             patch('telegram.upload_news',return_value=True), \
             patch('facebook.upload_news',return_value=True):
            report=pipeline.maybe_animated_bulletin(state,[bad,good],now,False)
        self.assertEqual(report['article_id'],'good')
        self.assertEqual(report['destinations']['telegram'],'accepted')

    def test_official_video_fallback_is_not_an_unreachable_return(self):
        article={'id':'video-story','title_si':'මාතර ප්‍රදේශයේ විශේෂ වීඩියෝ පුවත',
                 'published':time.time(),'summary_si':'මාතර ප්‍රදේශයේ අද පැවැති විශේෂ වැඩසටහනක් පිළිබඳ නිල වාර්තාවක් නිකුත් කර තිබේ.',
                 'link':'https://www.lankadeepa.lk/latest_news/video/1-123'}
        with patch('editorial.official_video_for',return_value='https://www.youtube.com/watch?v=X5LpOsYyDiU'):
            result=pipeline.share_official_video({},[article],time.time(),True)
        self.assertEqual(result['format'],'official_video_link')

    def test_official_video_link_sends_real_link_not_photo(self):
        from unittest.mock import MagicMock
        article={'id':'a','title_si':'මාතර පුවත්',
                 'summary_si':'මාතර ප්‍රදේශයේ අද නව පුවතක් පිළිබඳ විස්තර ප්‍රකාශ කර තිබේ.',
                 'published':time.time()}
        response=MagicMock(ok=True,status_code=200)
        response.json.return_value={'ok':True,'result':{'message_id':101}}
        with patch.dict(os.environ,{'TG_TOKEN':'dummy','TG_CHAT_ID':'dummy'}),patch('requests.post',return_value=response) as send:
            result=pipeline.send_official_video_link('telegram',article,'https://youtu.be/X5LpOsYyDiU')
        self.assertEqual(result['format'],'official_video_link')
        self.assertIn('youtube.com/watch',send.call_args.kwargs['json']['text'])
        self.assertNotIn('files',send.call_args.kwargs)

    def test_bulletin_throttled_and_only_after_real_news_receipts(self):
        article={'id':'a','title_si':'මාතර ප්‍රදේශයේ විශේෂ පුවතක්',
                 'summary_si':'මාතර ප්‍රදේශයේ අද සිදු වූ සිද්ධිය සම්බන්ධයෙන් නිලධාරීන් වැඩිදුර විමර්ශන ආරම්භ කර තිබේ.',
                 'published':time.time()}
        now=time.time()
        self.assertEqual(pipeline.maybe_animated_bulletin({'last_bulletin_at':now-10},[article],now,False),
                         'waiting_for_15_minute_bulletin_interval')
        with patch('animated_bulletin.render_bulletin') as render:
            self.assertEqual(pipeline.maybe_animated_bulletin({},[article],now,False),
                             'no_renderable_news_bulletin_candidate')
            render.assert_not_called()

    def test_original_bulletin_text_requires_factual_matching_summary(self):
        from animated_bulletin import narration_for
        article={'title_si':'මාතර ප්‍රදේශයේ විශේෂ සිද්ධියක්',
                 'summary_si':'මාතර ප්‍රදේශයේ විශේෂ සිද්ධියක් සම්බන්ධයෙන් පොලිසිය විමර්ශන ආරම්භ කර තිබේ.'}
        self.assertIn('මාතර',narration_for(article))
        with self.assertRaises(ValueError):
            narration_for(dict(article,summary_si=''))
