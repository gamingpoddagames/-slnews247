import json
import unittest
from source_photos import licensed_candidates

class SourcePhotosTests(unittest.TestCase):
    def test_only_explicitly_licensed_matching_article_images(self):
        link = 'https://sinhala.adaderana.lk/news/123'
        headline = 'මාතර පුවතක්'
        licensed = {'@type':'ImageObject', 'contentUrl':'/photo.jpg',
                    'license':'https://creativecommons.org/licenses/by/4.0/',
                    'creator':{'name':'Photographer'}}
        node = {'@type':'NewsArticle','headline':headline,
                'image':[licensed, dict(licensed, contentUrl='/second.jpg'),
                         dict(licensed, contentUrl='/no.jpg', license=''),
                         dict(licensed, contentUrl='https://other.example/photo.jpg')]}
        html = '<script type="application/ld+json">' + json.dumps(node) + '</script>'
        self.assertEqual(len(licensed_candidates(html, link, headline)), 2)
        self.assertEqual(licensed_candidates(html, link, 'වෙනත් පුවතක්'), [])
        self.assertEqual(licensed_candidates('<meta property="og:image" content="/photo.jpg">', link, headline), [])
