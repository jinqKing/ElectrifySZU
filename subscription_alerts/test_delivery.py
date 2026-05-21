from __future__ import annotations

import argparse
import time
from datetime import datetime
from pathlib import Path

from .email_service import EmailConfig, EmailService
from .email_templates import alert_content, alert_subject, verification_content, verification_subject
from .store import Subscription, now_iso

PROJECT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_ENV_FILE = PROJECT_DIR / ".env"


def build_test_subscription(email: str) -> Subscription:
    timestamp = now_iso()
    return Subscription(
        email=email.strip().lower(),
        client="192.168.84.87",
        campus_name="粤海",
        building_id="7126",
        building_name="风槐斋",
        room_name="713",
        threshold_kwh=20.0,
        enabled=True,
        verified=True,
        created_at=timestamp,
        updated_at=timestamp,
        verified_at=timestamp,
        verification_token="test-verification-token",
        verification_sent_at=timestamp,
        last_alert_date="",
        unsubscribe_token="test-unsubscribe-token",
    )


def build_test_alert_result() -> dict[str, object]:
    return {
        "room_name": "713",
        "remaining": 9.8,
        "last_record": datetime.now().date().isoformat(),
        "status": "critical",
    }


def send_verification_probe(service: EmailService, email: str, base_url: str) -> None:
    subscription = build_test_subscription(email)
    verification_url = f"{base_url.rstrip('/')}/api/subscriptions/verify?token={subscription.verification_token}"
    service.send_text(
        email,
        verification_subject(subscription),
        verification_content(subscription, verification_url),
    )


def send_alert_probe(service: EmailService, email: str, base_url: str) -> None:
    subscription = build_test_subscription(email)
    service.send_text(
        email,
        alert_subject(build_test_alert_result()),
        alert_content(subscription, build_test_alert_result(), base_url),
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Send delivery-test emails for the ElectrifySZU subscription pipeline."
    )
    parser.add_argument("--to", required=True, help="Recipient email address.")
    parser.add_argument(
        "--kind",
        choices=("verification", "alert", "both"),
        default="both",
        help="Which test email(s) to send.",
    )
    parser.add_argument(
        "--env",
        default=str(DEFAULT_ENV_FILE),
        help="Path to the project .env file.",
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8001",
        help="Base URL used in verify/unsubscribe links.",
    )
    parser.add_argument(
        "--loop-minutes",
        type=float,
        default=0,
        help="If greater than 0, keep sending at this interval in minutes.",
    )
    parser.add_argument(
        "--max-runs",
        type=int,
        default=0,
        help="Optional safety cap when looping. 0 means unlimited.",
    )
    parser.add_argument(
        "--show-config",
        action="store_true",
        help="Print the resolved SMTP config before sending.",
    )
    args = parser.parse_args()

    config = EmailConfig.from_env(args.env)
    if args.show_config:
        print(f"sender_name={config.sender_name}")
        print(f"sender_email={config.sender_email}")
        print(f"smtp_host={config.smtp_host}:{config.smtp_port}")
        print(f"smtp_ssl={config.smtp_ssl}")
        print(f"smtp_starttls={config.smtp_starttls}")

    service = EmailService(config)
    run_count = 0
    interval_seconds = max(args.loop_minutes, 0) * 60

    while True:
        run_count += 1
        timestamp = now_iso()
        print(f"[delivery-test] run={run_count} at {timestamp} kind={args.kind}")

        if args.kind in {"verification", "both"}:
            send_verification_probe(service, args.to, args.base_url)
            print(f"[delivery-test] verification email sent to {args.to}")

        if args.kind in {"alert", "both"}:
            send_alert_probe(service, args.to, args.base_url)
            print(f"[delivery-test] alert email sent to {args.to}")

        if interval_seconds <= 0:
            break
        if args.max_runs > 0 and run_count >= args.max_runs:
            break

        print(f"[delivery-test] sleeping {interval_seconds:g}s before next run")
        time.sleep(interval_seconds)


if __name__ == "__main__":
    main()
