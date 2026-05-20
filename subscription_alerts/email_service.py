import argparse
import os
import smtplib
import sys
from dataclasses import dataclass
from email.header import Header
from email.mime.text import MIMEText
from email.utils import formataddr
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
MONITOR_DIR = PROJECT_DIR / "room-power-monitor"
if str(MONITOR_DIR) not in sys.path:
    sys.path.insert(0, str(MONITOR_DIR))

from src.config import _load_dotenv

DEFAULT_ENV_FILE = PROJECT_DIR / ".env"


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


@dataclass(frozen=True)
class EmailConfig:
    smtp_host: str
    smtp_port: int
    smtp_ssl: bool
    smtp_starttls: bool
    sender_email: str
    sender_password: str
    sender_name: str = "电费预警系统"

    @classmethod
    def from_env(cls, env_path: str | os.PathLike[str] | None = None) -> "EmailConfig":
        _load_dotenv(str(env_path or DEFAULT_ENV_FILE))
        smtp_host = require_env("SMTP_HOST")
        if smtp_host in {"smtp.example.com", "example.com"}:
            raise RuntimeError("SMTP_HOST is still a placeholder.")

        sender_email = require_env("SENDER_EMAIL")
        if sender_email.endswith("@example.com"):
            raise RuntimeError("SENDER_EMAIL is still a placeholder.")

        sender_password = require_env("SENDER_PASSWORD")
        if sender_password == "your_email_authorization_code":
            raise RuntimeError("SENDER_PASSWORD is still a placeholder.")

        return cls(
            smtp_host=smtp_host,
            smtp_port=int(os.getenv("SMTP_PORT", "465")),
            smtp_ssl=env_bool("SMTP_SSL", True),
            smtp_starttls=env_bool("SMTP_STARTTLS", False),
            sender_email=sender_email,
            sender_password=sender_password,
            sender_name=os.getenv("SENDER_NAME", cls.sender_name),
        )


class EmailService:
    def __init__(self, config: EmailConfig | None = None):
        self.config = config or EmailConfig.from_env()

    def send_text(self, to_email: str, subject: str, content: str) -> None:
        message = MIMEText(content, "plain", "utf-8")
        message["From"] = formataddr(
            (str(Header(self.config.sender_name, "utf-8")), self.config.sender_email)
        )
        message["To"] = to_email
        message["Subject"] = Header(subject, "utf-8")

        if self.config.smtp_ssl:
            server = smtplib.SMTP_SSL(
                self.config.smtp_host,
                self.config.smtp_port,
                timeout=30,
            )
        else:
            server = smtplib.SMTP(
                self.config.smtp_host,
                self.config.smtp_port,
                timeout=30,
            )

        try:
            if self.config.smtp_starttls:
                server.starttls()
            server.login(self.config.sender_email, self.config.sender_password)
            server.sendmail(self.config.sender_email, [to_email], message.as_string())
        finally:
            server.quit()


def main() -> None:
    parser = argparse.ArgumentParser(description="Send a standalone ElectrifySZU test email.")
    parser.add_argument("--to", required=True, help="Recipient email address.")
    parser.add_argument("--subject", default="??????", help="Email subject.")
    parser.add_argument("--content", default="?????????", help="Email body.")
    parser.add_argument("--env", default=str(DEFAULT_ENV_FILE), help="Path to the project .env file.")
    parser.add_argument("--show-config", action="store_true", help="Print the resolved sender and SMTP settings before sending.")
    args = parser.parse_args()

    config = EmailConfig.from_env(args.env)
    if args.show_config:
        print(f"sender_name={config.sender_name}")
        print(f"sender_email={config.sender_email}")
        print(f"smtp_host={config.smtp_host}:{config.smtp_port}")
        print(f"smtp_ssl={config.smtp_ssl}")
        print(f"smtp_starttls={config.smtp_starttls}")

    EmailService(config).send_text(args.to, args.subject, args.content)
    print(f"sent to {args.to}")


if __name__ == "__main__":
    main()
