import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from story_visual import story_theme, story_facts, highlight, draw_story_hero


class StoryVisualAccuracyTests(unittest.TestCase):
    def setUp(self):
        self.article = {
            'id': 'teachers-strike',
            'title_si': 'නොවැම්බර් 30 ගුරු විදුහල්පති එක්දින වැඩ වර්ජනයක් සැලසුම්',
            'summary_si': (
                'නොවැම්බර් 30 වැනිදා එක්දින වැඩ වර්ජනයක් පැවැත්වීමට '
                'ගුරු හා විදුහල්පති සමිති තීරණය කර තිබේ. '
                '2027 අයවැයෙන් වැටුප් ඉල්ලීම්වලට විසඳුම් නොලැබුණු '
                'බව සමිති පවසයි. '
                'වර්ජනය තවම සිදු වී නැති බව වාර්තාවේ සඳහන් වේ.'
            ),
            'published': 1795351000,
        }

    def test_school_story_creates_correct_subject_and_headline_date(self):
        self.assertEqual(story_theme(self.article), ('education', 'අධ්‍යාපන'))
        self.assertEqual(highlight(self.article), ('30', 'නොවැම්බර්'))

    def test_only_factual_complete_sentences_enter_visual(self):
        facts = story_facts(self.article)
        self.assertEqual(len(facts), 3)
        self.assertIn('වර්ජනය', facts[0])
        self.assertTrue(all(fact in self.article['summary_si'] for fact in facts))
        self.assertEqual(story_facts({'summary_si': 'අසම්පූර්ණ විස්තරයක්'}), [])

    def test_story_hero_draws_nonempty_relevant_infographic(self):
        image = Image.new('RGB', (1080, 1350), '#000000')
        info = draw_story_hero(image, self.article, (46, 70, 1034, 822))
        self.assertEqual(info['highlight'], '30')
        self.assertEqual(info['topic'], 'education')
        self.assertIn('ගුරු', info['fact'])
        self.assertNotEqual(image.getpixel((230, 390)), (0, 0, 0))
        self.assertNotEqual(image.getpixel((700, 680)), (0, 0, 0))

    def test_real_photo_path_is_preserved_for_actual_matched_story(self):
        from image import news_card
        with tempfile.TemporaryDirectory() as tmp:
            photo = Path(tmp, 'real-event.jpg')
            Image.new('RGB', (1024, 768), 'red').save(photo)
            with patch('story_visual.draw_story_hero') as illustrate:
                result = news_card(self.article, image_path=str(photo))
            self.assertTrue(Path(result).exists())
            illustrate.assert_not_called()

    def test_reel_scene_receives_same_story_facts(self):
        from animated_bulletin import build_scene_images
        from story_visual import story_facts
        with tempfile.TemporaryDirectory() as tmp, \\
             patch('real_photo.select_real_photo',
                   return_value=(None, None, None)), \\
             patch('animated_bulletin._slide', side_effect=lambda *args, **kwargs: str(args[4])) as render:
            build_scene_images(self.article, 'approved', tmp)
        self.assertEqual(render.call_count, 3)
        expected = story_facts(self.article)
        self.assertEqual([call.args[1] for call in render.call_args_list], expected)


if __name__ == '__main__':
    unittest.main()
