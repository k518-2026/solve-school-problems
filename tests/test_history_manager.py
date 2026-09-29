import unittest
import tempfile
import json
from pathlib import Path
from src.history_manager import HistoryManager

class TestHistoryManager(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_dir = Path(self.temp_dir.name)
        self.history_path = self.base_dir / "history.json"
        self.log_path = self.base_dir / "POSTED_STORIES.md"
        self.catalog_path = self.base_dir / "topic_catalog.json"

        # Create sample catalog
        sample_catalog = {
            "pattern_A_topics": [
                {"id": "A01", "category": "学級経営", "problem_title": "指示待ち生徒"},
                {"id": "A02", "category": "授業改善", "problem_title": "グループワーク"}
            ],
            "pattern_B_topics": [
                {"id": "B01", "category": "校務自動化", "problem_title": "成績手計算"},
                {"id": "B02", "category": "ネットワーク", "problem_title": "Wi-Fi切断"}
            ],
            "pattern_C_topics": [
                {"id": "C01", "category": "いじめ重大事態", "problem_title": "いじめ被害の訴え"},
                {"id": "C02", "category": "懲戒と体罰の境界", "problem_title": "授業妨害生徒への対応"}
            ]
        }
        with open(self.catalog_path, "w", encoding="utf-8") as f:
            json.dump(sample_catalog, f)

        self.manager = HistoryManager(
            history_path=self.history_path,
            markdown_log_path=self.log_path,
            catalog_path=self.catalog_path
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_initial_pattern_is_A(self):
        # By default, first run starts with A
        self.assertEqual(self.manager.get_next_pattern(), "A")

    def test_pattern_alternation(self):
        # 1. Start at A
        p1 = self.manager.get_next_pattern()
        self.assertEqual(p1, "A")
        self.manager.record_post({"title": "Test Story 1", "pattern": "A", "topic_id": "A01"})

        # 2. Next should be B
        p2 = self.manager.get_next_pattern()
        self.assertEqual(p2, "B")
        self.manager.record_post({"title": "Test Story 2", "pattern": "B", "topic_id": "B01"})

        # 3. Next should be C
        p3 = self.manager.get_next_pattern()
        self.assertEqual(p3, "C")
        self.manager.record_post({"title": "Test Story 3", "pattern": "C", "topic_id": "C01"})

        # 4. Next should cycle back to A
        p4 = self.manager.get_next_pattern()
        self.assertEqual(p4, "A")

    def test_forced_pattern(self):
        # Force B even when initial
        p = self.manager.get_next_pattern(forced_pattern="B")
        self.assertEqual(p, "B")

        # Force C
        pc = self.manager.get_next_pattern(forced_pattern="C")
        self.assertEqual(pc, "C")

        # Force A
        p2 = self.manager.get_next_pattern(forced_pattern="a")
        self.assertEqual(p2, "A")

    def test_topic_selection(self):
        topic = self.manager.get_topic("A")
        self.assertEqual(topic["id"], "A01")

        # Specific topic ID for B
        topic2 = self.manager.get_topic("B", topic_id="B02")
        self.assertEqual(topic2["id"], "B02")

        # Topic for C
        topic3 = self.manager.get_topic("C")
        self.assertEqual(topic3["id"], "C01")

    def test_markdown_log_creation(self):
        self.manager.record_post({
            "title": "学級の課題解決",
            "pattern": "A",
            "topic_id": "A01",
            "category": "学級経営",
            "file_path": "content/test.md",
            "sent_to_wp": True
        })
        self.manager.record_post({
            "title": "学校法規の適用判断",
            "pattern": "C",
            "topic_id": "C01",
            "category": "いじめ重大事態",
            "file_path": "content/test_c.md",
            "sent_to_wp": True
        })
        self.assertTrue(self.log_path.exists())
        with open(self.log_path, "r", encoding="utf-8") as f:
            content = f.read()
            self.assertIn("Solve School Problems", content)
            self.assertIn("A (教育学)", content)
            self.assertIn("C (学校法制)", content)
            self.assertIn("学級の課題解決", content)
            self.assertIn("学校法規の適用判断", content)

if __name__ == "__main__":
    unittest.main()
