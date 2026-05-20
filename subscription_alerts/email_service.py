import os
import smtplib
from dataclasses import dataclass
from email.header import Header
from email.mime.text import MIMEText
from email.utils import formataddr

from src.config import _load_dotenv


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
    def from_env(cls, env_path: str = ".env") -> "EmailConfig":
        _load_dotenv(env_path)
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
