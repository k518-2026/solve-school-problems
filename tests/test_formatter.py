import unittest
from src.post_formatter import format_post_content, parse_frontmatter

class TestPostFormatter(unittest.TestCase):
    def test_parse_frontmatter(self):
        sample = """---
title: "生徒の意欲を引き出す対話"
pattern: "A"
category: "教育相談"
tags: ["教育心理学", "学級経営"]
---
ここから本文です。
"""
        meta, body = parse_frontmatter(sample)
        self.assertEqual(meta["title"], "生徒の意欲を引き出す対話")
        self.assertEqual(meta["pattern"], "A")
        self.assertEqual(meta["tags"], ["教育心理学", "学級経営"])
        self.assertEqual(body, "ここから本文です。")

    def test_format_post_pattern_a(self):
        sample = """---
title: "教室の沈黙を破る足場かけ"
pattern: "A"
---
### 【作中理論・教育学のやさしい解説（Theoretical Commentary）】
最近接発達領域（ZPD）の解説。

### 【引用・参考文献（Academic References）】
1. Vygotsky (1978). [https://doi.org/10.1000/182](https://doi.org/10.1000/182)
"""
        post = format_post_content(sample, default_status="publish", use_jetpack_shortcodes=True)
        self.assertEqual(post.title, "教室の沈黙を破る足場かけ")
        self.assertEqual(post.pattern, "A")
        self.assertIn("[category 教育相談・学級経営, 教育心理学・教育哲学]", post.content_plain)
        self.assertIn("[status publish]", post.content_plain)
        self.assertNotIn("パターンA：新米教員 × 先輩教員", post.content_html)
        self.assertIn('target="_blank"', post.content_html)
        self.assertIn("https://doi.org/10.1000/182", post.content_html)

    def test_format_post_pattern_b(self):
        sample = """---
title: "GASによる成績集計の革命"
pattern: "B"
---
若手教員がスクリプトを実行した。

```javascript
function calculateGrades() {
    Logger.log("Done");
}
```

参考リンク: https://developers.google.com/apps-script
"""
        post = format_post_content(sample, default_status="publish", use_jetpack_shortcodes=True)
        self.assertEqual(post.pattern, "B")
        self.assertNotIn("パターンB：年配教員 × 若手教員", post.content_html)
        self.assertIn('target="_blank"', post.content_html)
        self.assertIn("<code>function calculateGrades()", post.content_html)
        self.assertIn('<a href="https://developers.google.com/apps-script" target="_blank"', post.content_html)

if __name__ == "__main__":
    unittest.main()
