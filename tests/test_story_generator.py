import unittest
from src.story_generator import StoryGenerator

class TestStoryGenerator(unittest.TestCase):
    def test_fallback_pattern_a(self):
        generator = StoryGenerator(api_key=None)
        topic = {
            "id": "A01",
            "category": "学級経営",
            "problem_title": "指示待ち生徒への対応"
        }
        content, title, refs = generator.generate_story("A", topic)
        self.assertIn("pattern: \"A\"", content)
        self.assertIn("自己決定理論", content)
        self.assertIn("【作中理論・教育学のやさしい解説", content)
        self.assertIn("【引用・参考文献", content)
        self.assertTrue(len(refs) > 0)
        self.assertTrue(len(title) > 0)

    def test_fallback_pattern_b(self):
        generator = StoryGenerator(api_key=None)
        topic = {
            "id": "B01",
            "category": "校務自動化",
            "problem_title": "成績手計算ミス"
        }
        content, title, refs = generator.generate_story("B", topic)
        self.assertIn("pattern: \"B\"", content)
        self.assertIn("Google Apps Script", content)
        self.assertIn("【作中技術・ITネットワークのやさしい解説", content)
        self.assertIn("【引用・参考文献", content)
        self.assertTrue(len(refs) > 0)
        self.assertTrue(len(title) > 0)

if __name__ == "__main__":
    unittest.main()
