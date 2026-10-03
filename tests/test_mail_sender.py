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
            blogger_post_email="user.secret@blogger.com",
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
            content_plain="[category 教育相談]\n[tags 教育学]\n[status publish]\n\nプレーンテキスト本文"
        )
        msg = self.sender.create_mime_message(post)
        self.assertIn("テスト記事タイトル", str(msg["Subject"]))
        self.assertIn("sender@example.com", msg["From"])
        self.assertEqual(msg["To"], "secret-wp@post.wordpress.com")

    def test_create_blogger_mime_message_strips_shortcodes_links_and_styles(self):
        post = FormattedPost(
            title="Bloggerテスト記事",
            pattern="B",
            categories=["校務DX"],
            tags=["GAS"],
            status="publish",
            content_html=(
                '<div class="ssp-post-wrapper" style="font-family: sans-serif;">'
                '<p style="margin: 0;">Blogger HTML本文 <a href="https://doi.org/10.1037/0003-066X.55.1.68" style="color: blue;">https://doi.org/10.1037/0003-066X.55.1.68</a></p>'
                '<div style="text-align: center;">◆　◆　◆</div>'
                '</div>'
            ),
            content_plain="[category 校務DX]\n[tags GAS]\n[status publish]\n\nBloggerプレーンテキスト本文 https://example.com/test"
        )
        msg = self.sender.create_mime_message(post, recipient="user.secret@blogger.com", is_blogger=True)
        self.assertEqual(msg["To"], "user.secret@blogger.com")
        self.assertIsNotNone(msg["Date"])
        self.assertIsNotNone(msg["Message-ID"])

        plain_payload = msg.get_payload()[0].get_payload(decode=True).decode("utf-8")
        html_payload = msg.get_payload()[1].get_payload(decode=True).decode("utf-8")

        self.assertNotIn("[category", plain_payload)
        self.assertNotIn("[status", plain_payload)
        self.assertNotIn("https://example.com/test", plain_payload)
        self.assertIn("Bloggerプレーンテキスト本文", plain_payload)

        # Blogger HTML must strip <a> tags, raw https:// URLs, style attributes, and <div> wrappers
        self.assertNotIn("<a ", html_payload)
        self.assertNotIn("https://", html_payload)
        self.assertNotIn("style=", html_payload)
        self.assertNotIn("<div", html_payload)
        self.assertIn("DOI: 10.1037/0003-066X.55.1.68", html_payload)
        self.assertIn("Blogger HTML本文", html_payload)

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
        self.assertEqual(result["blogger_to"], "user.secret@blogger.com")

if __name__ == "__main__":
    unittest.main()
