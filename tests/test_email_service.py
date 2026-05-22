from __future__ import annotations

import smtplib
import socket
from pathlib import Path

import pytest

from subscription_alerts.email_service import EmailConfig, EmailDeliveryError, EmailService


def write_env(path: Path, content: str) -> Path:
    path.write_text(content.strip() + "\n", encoding="utf-8")
    return path


def test_email_config_rejects_placeholder_smtp_host(tmp_path: Path, monkeypatch) -> None:
    env_path = write_env(
        tmp_path / ".env",
        """
        SMTP_HOST=smtp.example.com
        SENDER_EMAIL=warning@example.com
        SENDER_PASSWORD=your_email_authorization_code
        """,
    )
    monkeypatch.delenv("SMTP_HOST", raising=False)
    monkeypatch.delenv("SENDER_EMAIL", raising=False)
    monkeypatch.delenv("SENDER_PASSWORD", raising=False)

    with pytest.raises(RuntimeError):
        EmailConfig.from_env(env_path)


def test_send_once_uses_ssl_server(monkeypatch) -> None:
    events: list[tuple[str, object]] = []

    class FakeSMTP:
        def login(self, email, password):
            events.append(("login", email))

        def sendmail(self, sender, recipients, message):
            events.append(("sendmail", sender))
            return {}

        def quit(self):
            events.append(("quit", None))

    monkeypatch.setattr(
        "subscription_alerts.email_service.smtplib.SMTP_SSL",
        lambda host, port, timeout: FakeSMTP(),
    )

    service = EmailService(
        EmailConfig(
            smtp_host="smtp.test",
            smtp_port=465,
            smtp_ssl=True,
            smtp_starttls=False,
            sender_email="sender@test.com",
            sender_password="secret",
            sender_name="Tester",
        )
    )
    service._send_once("dest@test.com", service._build_message("dest@test.com", "Subject", "Body"))

    assert events == [("login", "sender@test.com"), ("sendmail", "sender@test.com"), ("quit", None)]


def test_send_text_retries_transient_errors(monkeypatch) -> None:
    attempts: list[int] = []

    def fake_send_once(self, to_email, message):
        attempts.append(1)
        if len(attempts) < 3:
            raise socket.timeout("timeout")

    monkeypatch.setattr(EmailService, "_send_once", fake_send_once)
    monkeypatch.setattr("subscription_alerts.email_service.time.sleep", lambda seconds: None)
    monkeypatch.setattr("subscription_alerts.email_service.random.uniform", lambda a, b: 0.0)

    service = EmailService(
        EmailConfig(
            smtp_host="smtp.test",
            smtp_port=465,
            smtp_ssl=True,
            smtp_starttls=False,
            sender_email="sender@test.com",
            sender_password="secret",
            sender_name="Tester",
        )
    )
    service.send_text("dest@test.com", "Subject", "Body")

    assert len(attempts) == 3


def test_send_text_converts_recipient_refused(monkeypatch) -> None:
    def fake_send_once(self, to_email, message):
        raise smtplib.SMTPRecipientsRefused({"dest@test.com": (550, "denied")})

    monkeypatch.setattr(EmailService, "_send_once", fake_send_once)

    service = EmailService(
        EmailConfig(
            smtp_host="smtp.test",
            smtp_port=465,
            smtp_ssl=True,
            smtp_starttls=False,
            sender_email="sender@test.com",
            sender_password="secret",
            sender_name="Tester",
        )
    )

    with pytest.raises(EmailDeliveryError):
        service.send_text("dest@test.com", "Subject", "Body")
