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
    ollama_host: str = "http://192.168.128.59:11434"
    writer_model: str = "shosetsu"
    draw_things_host: str = "http://192.168.128.59:7860"

def get_config() -> SMTPConfig:
    """Retrieve and parse configuration from environment variables."""
    user = os.getenv("SMTP_USER", "").strip()
    raw_host = os.getenv("SMTP_HOST", "").strip()
    if raw_host:
        host = raw_host
    elif any(user.lower().endswith(d) for d in ("@outlook.com", "@hotmail.com", "@live.com", "@outlook.jp")):
        host = "smtp-mail.outlook.com"
    else:
        host = "smtp.gmail.com"
    port = int(os.getenv("SMTP_PORT", "587"))
    password = os.getenv("SMTP_PASSWORD", "").strip()
    use_tls = os.getenv("SMTP_USE_TLS", "true").lower() in ("true", "1", "yes")
    use_ssl = os.getenv("SMTP_USE_SSL", "false").lower() in ("true", "1", "yes")
    from_name = os.getenv("MAIL_FROM_NAME", "Solve School Problems").strip()
    # Temporarily pause WordPress posting by default (set ENABLE_WP_POST=true to re-enable)
    enable_wp = os.getenv("ENABLE_WP_POST", "false").strip().lower() in ("true", "1", "yes")
    wp_post_email = os.getenv("WP_POST_EMAIL", "").strip() if enable_wp else ""
    blogger_post_email = os.getenv("BLOGGER_POST_EMAIL", "").strip()
    default_status = os.getenv("DEFAULT_POST_STATUS", "publish").strip()
    use_jetpack_shortcodes = os.getenv("USE_JETPACK_SHORTCODES", "true").lower() in ("true", "1", "yes")
    ollama_host = os.getenv("OLLAMA_HOST", "http://192.168.128.59:11434").strip()
    writer_model = os.getenv("OLLAMA_WRITER_MODEL", "shosetsu").strip()
    draw_things_host = os.getenv("DRAW_THINGS_HOST", "http://192.168.128.59:7860").strip()

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
        ollama_host=ollama_host,
        writer_model=writer_model,
        draw_things_host=draw_things_host,
    )
