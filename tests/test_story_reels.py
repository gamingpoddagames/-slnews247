import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from story_reels import publish_reels


class PerStoryReelTests(unittest.TestCase):
    def setUp(self):
        self.article = {
            'id': 'event-one',
            'title_si': 'මාතර ප්‍රදේශයේ නිවේදනයක්',
            'summary_si': 'මාතර ප්‍රදේශයේ නිවේදනයක් නිකුත් වී තිබේ. එහි අවශ්‍ය කරුණු නිලධාරීන් විසින් පැහැදිලි කර තිබේ.',
            'published': 1795350000,
            'link': 'https://example.com/news/1',
        }
        self.state = {
            'stories': {'event-one': {'receipts': {
                'telegram': {'id': '1'}, 'facebook': {'id': '2'}}}}
        }

    def test_branded_reel_delivered_once_to_both_channels(self):
        events = []
        with tempfile.TemporaryDirectory() as folder, \
             patch('fast_news.publishable', return_value=True), \
             patch('animated_bulletin.narration_for', return_value='Sinhala narration'), \
             patch('animated_bulletin.render_bulletin', return_value=str(Path(folder) / 'reel.mp4')) as renderer, \
             patch('story_reels._media_attribution', return_value=''), \
             patch('fast_news.save'), \
             patch('telegram.upload_video', side_effect=lambda path, caption: events.append('telegram') or True), \
             patch('facebook.upload_video', side_effect=lambda path, caption: events.append('facebook') or True):
            first = publish_reels(self.state, [self.article], 1795350300)
            second = publish_reels(self.state, [self.article], 1795350310)
        self.assertEqual(first['sent'], {'telegram': 1, 'facebook': 1})
        self.assertEqual(second['sent'], {'telegram': 0, 'facebook': 0})
        self.assertEqual(events, ['telegram', 'facebook'])
        self.assertEqual(renderer.call_count, 1)
        self.assertEqual(self.state['reels']['event-one']['status'], 'delivered')

    def test_no_image_receipts_means_no_reel(self):
        with patch('fast_news.publishable', return_value=True), \
             patch('animated_bulletin.render_bulletin') as render:
            out = publish_reels({}, [self.article], 1795350300)
        self.assertEqual(out['rendered'], 0)
        render.assert_not_called()

    def test_uncertain_upload_not_blindly_retried(self):
        with patch('fast_news.publishable', return_value=True), \
             patch('animated_bulletin.narration_for', return_value='Narration'), \
             patch('animated_bulletin.render_bulletin', return_value='output/reel.mp4'), \
             patch('story_reels._media_attribution', return_value=''), \
             patch('fast_news.save'), \
             patch('telegram.upload_video', return_value=False) as telegram, \
             patch('facebook.upload_video', return_value=True):
            out = publish_reels(self.state, [self.article], 1795350300)
            followup = publish_reels(self.state, [self.article], 1795350600)
        self.assertEqual(out['failed_or_uncertain'], 1)
        self.assertEqual(followup['rendered'], 0)
        telegram.assert_called_once()

    def test_approved_exact_clip_is_preferred_over_graphic_reel(self):
        from story_reels import render_story_reel
        with patch('media.choose_video', return_value='real-event.mp4'), \
             patch('voice.create_voice', return_value=True), \
             patch('animated_bulletin.narration_for', return_value='Factual Sinhala script'), \
             patch('video.create_footage_video', return_value=True) as encode, \
             patch('animated_bulletin.render_bulletin') as graphic:
            path, mode = render_story_reel(self.article, 'output/reels/one.mp4')
        self.assertEqual(mode, 'verified_event_clip')
        self.assertEqual(path, 'output/reels/one.mp4')
        encode.assert_called_once()
        graphic.assert_not_called()

    def test_unavailable_approved_clip_uses_branded_reel(self):
        from story_reels import render_story_reel
        with patch('media.choose_video', return_value=None), \
             patch('animated_bulletin.render_bulletin', return_value='graphic.mp4'):
            path, mode = render_story_reel(self.article, 'graphic.mp4')
        self.assertEqual((path, mode),
                         ('graphic.mp4', 'original_graphic_or_verified_photo'))

    def test_queued_story_still_gets_reel_after_it_disappears_from_rss(self):
        second = dict(self.article, id='event-two',
                      published=self.article['published'] + 3)
        self.state['stories']['event-two'] = {
            'receipts': {'telegram': {'id': '3'}, 'facebook': {'id': '4'}}}
        with patch('fast_news.publishable', return_value=True), \
             patch('media.choose_video', return_value=None), \
             patch('animated_bulletin.render_bulletin', return_value='mock.mp4') as renderer, \
             patch('story_reels._media_attribution', return_value=''), \
             patch('fast_news.save'), \
             patch('telegram.upload_video', return_value=True) as tg, \
             patch('facebook.upload_video', return_value=True) as fb:
            first = publish_reels(self.state, [self.article, second],
                                  1795350300, max_per_run=1)
            # Second story is no longer in the fresh feed, but queued.
            followup = publish_reels(self.state, [],
                                     1795350600, max_per_run=1)
        self.assertEqual(first['pending'], 1)
        self.assertEqual(followup['sent'], {'telegram': 1, 'facebook': 1})
        self.assertEqual(self.state['reels']['event-two']['status'], 'delivered')
        self.assertEqual(renderer.call_count, 2)
        self.assertEqual(tg.call_count, 2)
        self.assertEqual(fb.call_count, 2)

    def test_old_bulletin_is_not_posted_again_as_reel(self):
        self.state['bulletins'] = {'event-one': {
            'destinations': {'telegram': 'accepted', 'facebook': 'accepted'}}}
        with patch('fast_news.publishable', return_value=True), \
             patch('animated_bulletin.render_bulletin') as renderer, \
             patch('fast_news.save'):
            result = publish_reels(self.state, [self.article], 1795350300)
        self.assertEqual(result['sent'], {'telegram': 0, 'facebook': 0})
        self.assertEqual(self.state['reels']['event-one']['status'],
                         'delivered_earlier')
        renderer.assert_not_called()

    def test_online_voice_failure_uses_original_graphic_video(self):
        from story_reels import _render_reel
        with patch('media.choose_video', return_value=None), \
             patch('animated_bulletin.render_bulletin',
                   side_effect=RuntimeError('TTS unavailable')), \
             patch('animated_bulletin.render_graphic_reel',
                   return_value='graphic.mp4') as fallback:
            result = _render_reel(self.article, 'graphic.mp4')
        self.assertEqual(result, ('graphic.mp4', 'branded_graphic_reel'))
        fallback.assert_called_once()

    def test_reel_boundary_survives_checkpoint_merge(self):
        from scripts.merge_news_checkpoint import merge_state
        remote = {'reels_started_at': 100, 'reels': {
            'a': {'status': 'queued', 'article': self.article}}}
        local = {'reels_started_at': 120, 'reels': {
            'b': {'status': 'queued', 'article': self.article}}}
        result = merge_state(remote, local)
        self.assertEqual(result['reels_started_at'], 100)
        self.assertEqual(set(result['reels']), {'a', 'b'})

    def test_attribution_added_for_copyright_licensed_bank_image(self):
        from story_reels import _media_attribution
        credit = {'label_si': 'ශ්‍රී ලංකා මහ බැංකුවේ ගොඩනැගිල්ල',
                  'creator': 'Zsastaba', 'license': 'CC BY 4.0',
                  'source': 'https://commons.wikimedia.org/wiki/File:Sri_lanka2024.png',
                  'license_url': 'https://creativecommons.org/licenses/by/4.0/'}
        with patch('real_photo.select_real_photo',
                   return_value=('bank.jpg', 'verified_institution_photo', credit)):
            public = _media_attribution({'title_si': 'මහ බැංකුව පොලී තීරණය'})
        self.assertIn('Zsastaba', public)
        self.assertIn('CC BY 4.0', public)


if __name__ == '__main__':
    unittest.main()
