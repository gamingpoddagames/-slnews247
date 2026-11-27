import unittest
from subject_photos import rule_for
class SubjectPhotoTests(unittest.TestCase):
    def test_explicit_subject_only(self):
        self.assertIsNotNone(rule_for('තරුණයින්ට වෘත්තීය පුහුණුව ලබාදීමට වැඩසටහනක්'))
        self.assertIsNotNone(rule_for('ක්‍රිකට් තරගයක්'))
        self.assertIsNone(rule_for('ක්‍රිකට් ක්‍රීඩකයෙකු අත්අඩංගුවට'))
        self.assertIsNone(rule_for('නවතම පුවත'))
