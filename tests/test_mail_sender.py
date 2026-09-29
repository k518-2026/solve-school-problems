import unittest
from src.config import SMTPConfig
from src.post_formatter import FormattedPost
from src.mail_sender import WordPressMailSender

class TestWordPressMailSender(unittest.TestCase):
    def setUp(self):
        self.config = SMTPConfig(
            host="smtp.example.com",
            port=587,
            user="sender@example.com",
            password="secret_password",
            use_tls=True,
            use_ssl=False,
            from_name="Solve School Problems Bot",
            wp_post_email="secret-wp@post.wordpress.com",
            default_status="publish",
            use_jetpack_shortcodes=True
        )
        self.sender = WordPressMailSender(self.config)

    def test_create_mime_message(self):
        post = FormattedPost(
            title="テスト記事タイトル",
            pattern="A",
            categories=["教育相談"],
            tags=["教育学"],
            status="publish",
            content_html="<p>HTML本文</p>",
            content_plain="プレーンテキスト本文"
        )
        msg = self.sender.create_mime_message(post)
        self.assertIn("テスト記事タイトル", str(msg["Subject"]))
        self.assertIn("sender@example.com", msg["From"])
        self.assertEqual(msg["To"], "secret-wp@post.wordpress.com")

    def test_dry_run_mode(self):
        post = FormattedPost(
            title="ドライランテスト",
            pattern="B",
            content_html="<p>テスト</p>",
            content_plain="テスト"
        )
        result = self.sender.send_post(post, dry_run=True)
        self.assertTrue(result["success"])
        self.assertTrue(result["dry_run"])
        self.assertEqual(result["title"], "ドライランテスト")

if __name__ == "__main__":
    unittest.main()
