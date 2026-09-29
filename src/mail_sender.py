import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.header import Header
from typing import Dict, Any, Optional
import logging

from src.config import SMTPConfig
from src.post_formatter import FormattedPost

logger = logging.getLogger(__name__)

class WordPressMailSender:
    """
    Sends posts to WordPress via Email using standard SMTP.
    Supports Jetpack Post by Email, Postie, and standard WP mail receivers.
    """

    def __init__(self, config: SMTPConfig):
        self.config = config

    def create_mime_message(self, post: FormattedPost) -> MIMEMultipart:
        """Constructs a MIMEMultipart email message with text and HTML parts."""
        msg = MIMEMultipart("alternative")
        
        # Subject becomes the WordPress Post Title
        msg["Subject"] = Header(post.title, "utf-8")
        
        # From header
        from_display = Header(self.config.from_name, "utf-8").encode()
        msg["From"] = f"{from_display} <{self.config.user}>"
        
        # Destination: WordPress Post by Email secret inbox
        msg["To"] = self.config.wp_post_email

        # Attach text part and HTML part
        part_text = MIMEText(post.content_plain, "plain", "utf-8")
        part_html = MIMEText(post.content_html, "html", "utf-8")
        
        msg.attach(part_text)
        msg.attach(part_html)

        return msg

    def send_post(
        self,
        post: FormattedPost,
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Sends the formatted post to the WordPress mail receiver.
        If dry_run is True, skips actual network dispatch and logs details.
        """
        msg = self.create_mime_message(post)

        if dry_run or not self.config.wp_post_email or not self.config.user:
            logger.info("================ [DRY RUN / MOCK MODE] ================")
            logger.info(f"Target WP Email: {self.config.wp_post_email or '(Not Set - WP_POST_EMAIL)'}")
            logger.info(f"Subject (WP Title): {post.title}")
            logger.info(f"From: {self.config.user or '(Not Set - SMTP_USER)'}")
            logger.info(f"Pattern: {post.pattern}")
            logger.info(f"Status: {post.status}")
            logger.info(f"Categories: {', '.join(post.categories)}")
            logger.info(f"Tags: {', '.join(post.tags)}")
            logger.info(f"HTML Content Length: {len(post.content_html)} chars")
            logger.info("========================================================")
            return {
                "success": True,
                "dry_run": True,
                "title": post.title,
                "to": self.config.wp_post_email,
                "message": "Dry run completed successfully. No actual email sent."
            }

        logger.info(f"Connecting to SMTP server {self.config.host}:{self.config.port}...")
        
        try:
            if self.config.use_ssl:
                context = ssl.create_default_context()
                with smtplib.SMTP_SSL(self.config.host, self.config.port, context=context) as server:
                    if self.config.user and self.config.password:
                        server.login(self.config.user, self.config.password)
                    server.sendmail(self.config.user, [self.config.wp_post_email], msg.as_string())
            else:
                with smtplib.SMTP(self.config.host, self.config.port) as server:
                    server.ehlo()
                    if self.config.use_tls:
                        context = ssl.create_default_context()
                        server.starttls(context=context)
                        server.ehlo()
                    if self.config.user and self.config.password:
                        server.login(self.config.user, self.config.password)
                    server.sendmail(self.config.user, [self.config.wp_post_email], msg.as_string())

            logger.info(f"Successfully dispatched post '{post.title}' to {self.config.wp_post_email}")
            return {
                "success": True,
                "dry_run": False,
                "title": post.title,
                "to": self.config.wp_post_email,
                "message": "Post successfully sent to WordPress."
            }
        except Exception as e:
            logger.error(f"Failed to dispatch post via SMTP: {e}", exc_info=True)
            return {
                "success": False,
                "dry_run": False,
                "title": post.title,
                "to": self.config.wp_post_email,
                "error": str(e)
            }
