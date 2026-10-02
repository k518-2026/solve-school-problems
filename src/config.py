import os
from dataclasses import dataclass
from pathlib import Path

# Safe optional import of dotenv
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # Lightweight fallback parser for .env
    env_file = Path(".env")
    if env_file.exists():
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip("'\"")
                    if key and key not in os.environ:
                        os.environ[key] = val

@dataclass
class SMTPConfig:
    host: str
    port: int
    user: str
    password: str
    use_tls: bool
    use_ssl: bool
    from_name: str
    wp_post_email: str
    default_status: str
    use_jetpack_shortcodes: bool
    blogger_post_email: str = ""

def get_config() -> SMTPConfig:
    """Retrieve and parse configuration from environment variables."""
    host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER", "")
    password = os.getenv("SMTP_PASSWORD", "")
    use_tls = os.getenv("SMTP_USE_TLS", "true").lower() in ("true", "1", "yes")
    use_ssl = os.getenv("SMTP_USE_SSL", "false").lower() in ("true", "1", "yes")
    from_name = os.getenv("MAIL_FROM_NAME", "Solve School Problems")
    wp_post_email = os.getenv("WP_POST_EMAIL", "")
    blogger_post_email = os.getenv("BLOGGER_POST_EMAIL", "")
    default_status = os.getenv("DEFAULT_POST_STATUS", "publish")
    use_jetpack_shortcodes = os.getenv("USE_JETPACK_SHORTCODES", "true").lower() in ("true", "1", "yes")

    return SMTPConfig(
        host=host,
        port=port,
        user=user,
        password=password,
        use_tls=use_tls,
        use_ssl=use_ssl,
        from_name=from_name,
        wp_post_email=wp_post_email,
        default_status=default_status,
        use_jetpack_shortcodes=use_jetpack_shortcodes,
        blogger_post_email=blogger_post_email,
    )
