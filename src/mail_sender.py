import re
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.header import Header
from typing import Dict, Any, Optional, List
import logging

from src.config import SMTPConfig
from src.post_formatter import FormattedPost

logger = logging.getLogger(__name__)

class WordPressMailSender:
    """
    Sends posts to WordPress and Blogger via Email using standard SMTP.
    Supports Jetpack Post by Email, Postie, standard WP mail receivers,
    and Google Blogger "Post using email" (username.secret@blogger.com).
    """

    def __init__(self, config: SMTPConfig):
        self.config = config

    @staticmethod
    def _strip_jetpack_shortcodes(plain_text: str) -> str:
        """Removes Jetpack [category ...], [tags ...], [status ...] shortcodes for Blogger."""
        lines = plain_text.splitlines()
        cleaned = []
        skip_leading_blank = True
        for line in lines:
            if re.match(r"^\[(category|tags|status)\s+.*\]$", line.strip(), flags=re.IGNORECASE):
                continue
            if skip_leading_blank and not line.strip():
                continue
            skip_leading_blank = False
            cleaned.append(line)
        return "\n".join(cleaned)

    def create_mime_message(
        self,
        post: FormattedPost,
        recipient: Optional[str] = None,
        is_blogger: bool = False
    ) -> MIMEMultipart:
        """Constructs a MIMEMultipart email message with text and HTML parts."""
        msg = MIMEMultipart("alternative")

        target_to = recipient if recipient is not None else self.config.wp_post_email
        if target_to and "@blogger.com" in target_to.lower():
            is_blogger = True

        # Subject becomes the WordPress / Blogger Post Title
        msg["Subject"] = Header(post.title, "utf-8")

        # From header
        from_display = Header(self.config.from_name, "utf-8").encode()
        msg["From"] = f"{from_display} <{self.config.user}>"

        # Destination inbox
        msg["To"] = target_to

        # Attach text part (strip Jetpack shortcodes if destination is Blogger) and HTML part
        plain_body = self._strip_jetpack_shortcodes(post.content_plain) if is_blogger else post.content_plain
        part_text = MIMEText(plain_body, "plain", "utf-8")
        part_html = MIMEText(post.content_html, "html", "utf-8")

        msg.attach(part_text)
        msg.attach(part_html)

        return msg

    @staticmethod
    def _parse_email_list(raw_emails: str) -> List[str]:
        if not raw_emails:
            return []
        return [e.strip() for e in raw_emails.split(",") if e.strip()]

    def send_post(
        self,
        post: FormattedPost,
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Sends the formatted post to WordPress (WP_POST_EMAIL) and/or Blogger (BLOGGER_POST_EMAIL).
        If dry_run is True, skips actual network dispatch and logs details.
        """
        wp_targets = self._parse_email_list(self.config.wp_post_email)
        blogger_targets = self._parse_email_list(self.config.blogger_post_email)

        # Also auto-classify any @blogger.com address placed inside WP_POST_EMAIL
        all_targets = []
        for addr in wp_targets:
            is_bg = "@blogger.com" in addr.lower()
            all_targets.append((addr, "blogger" if is_bg else "wp", is_bg))
        for addr in blogger_targets:
            if not any(existing[0].lower() == addr.lower() for existing in all_targets):
                all_targets.append((addr, "blogger", True))

        if dry_run or not all_targets or not self.config.user:
            logger.info("================ [DRY RUN / MOCK MODE] ================")
            logger.info(f"Target WP Email: {self.config.wp_post_email or '(Not Set - WP_POST_EMAIL)'}")
            logger.info(f"Target Blogger Email: {self.config.blogger_post_email or '(Not Set - BLOGGER_POST_EMAIL)'}")
            logger.info(f"Subject (Post Title): {post.title}")
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
                "blogger_to": self.config.blogger_post_email,
                "sent_to_wp": False,
                "sent_to_blogger": False,
                "message": "Dry run completed successfully. No actual email sent."
            }

        logger.info(f"Connecting to SMTP server {self.config.host}:{self.config.port}...")

        sent_wp = False
        sent_blogger = False
        errors: List[str] = []

        try:
            if self.config.use_ssl:
                context = ssl.create_default_context()
                server_ctx = smtplib.SMTP_SSL(self.config.host, self.config.port, context=context)
            else:
                server_ctx = smtplib.SMTP(self.config.host, self.config.port)

            with server_ctx as server:
                if not self.config.use_ssl:
                    server.ehlo()
                    if self.config.use_tls:
                        context = ssl.create_default_context()
                        server.starttls(context=context)
                        server.ehlo()
                if self.config.user and self.config.password:
                    server.login(self.config.user, self.config.password)

                for addr, platform, is_blogger in all_targets:
                    try:
                        msg = self.create_mime_message(post, recipient=addr, is_blogger=is_blogger)
                        server.sendmail(self.config.user, [addr], msg.as_string())
                        platform_label = "Blogger" if is_blogger else "WordPress"
                        logger.info(f"Successfully dispatched post '{post.title}' to {platform_label} ({addr})")
                        if is_blogger:
                            sent_blogger = True
                        else:
                            sent_wp = True
                    except Exception as target_err:
                        err_str = f"{addr}: {target_err}"
                        logger.error(f"Failed to dispatch post to {addr}: {target_err}", exc_info=True)
                        errors.append(err_str)

            overall_success = sent_wp or sent_blogger
            return {
                "success": overall_success,
                "dry_run": False,
                "title": post.title,
                "to": self.config.wp_post_email,
                "blogger_to": self.config.blogger_post_email,
                "sent_to_wp": sent_wp,
                "sent_to_blogger": sent_blogger,
                "errors": errors,
                "message": "Post successfully dispatched." if overall_success else "; ".join(errors)
            }
        except Exception as e:
            logger.error(f"Failed to dispatch post via SMTP: {e}", exc_info=True)
            return {
                "success": False,
                "dry_run": False,
                "title": post.title,
                "to": self.config.wp_post_email,
                "blogger_to": self.config.blogger_post_email,
                "sent_to_wp": sent_wp,
                "sent_to_blogger": sent_blogger,
                "error": str(e)
            }
