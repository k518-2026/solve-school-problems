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

    def test_fallback_pattern_c(self):
        generator = StoryGenerator(api_key=None)
        topic = {
            "id": "C01",
            "category": "いじめ重大事態",
            "problem_title": "いじめ重大事態の初動と学校の法的責務"
        }
        content, title, refs = generator.generate_story("C", topic)
        self.assertIn("pattern: \"C\"", content)
        self.assertIn("いじめ防止対策推進法", content)
        self.assertIn("【作中法規・教育法制のやさしい解説", content)
        self.assertIn("【引用・参考文献", content)
        self.assertTrue(len(refs) > 0)
        self.assertTrue(len(title) > 0)

if __name__ == "__main__":
    unittest.main()
