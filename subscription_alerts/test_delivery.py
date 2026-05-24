from __future__ import annotations

import argparse
import logging
import os
import time
from datetime import datetime
from pathlib import Path

from .email_service import EmailConfig, EmailService
from .email_templates import alert_content, alert_subject, verification_content, verification_subject
from .store import Subscription, now_iso

logger = logging.getLogger("test_delivery")

PROJECT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_ENV_FILE = PROJECT_DIR / ".env"


def _env_str(name: str, default: str) -> str:
    val = os.getenv(name)
    return val.strip() if val and val.strip() else default


def build_test_subscription(email: str) -> Subscription:
    timestamp = now_iso()
    return Subscription(
        email=email.strip().lower(),
        client=_env_str("TEST_CLIENT_IP", "192.168.84.87"),
        campus_name=_env_str("TEST_BUILDING_CAMPUS", "粤海"),
        building_id="7126",
        building_name=_env_str("TEST_BUILDING_NAME", "风槐斋"),
        room_name=_env_str("TEST_ROOM_NAME", "713"),
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
        default=None,
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
    base_url = args.base_url or os.getenv("PUBLIC_BASE_URL", "http://127.0.0.1:8000")
    if args.show_config:
        logger.info("sender_name=%s", config.sender_name)
        logger.info("sender_email=%s", config.sender_email)
        logger.info("smtp_host=%s:%d", config.smtp_host, config.smtp_port)
        logger.info("smtp_ssl=%s", config.smtp_ssl)
        logger.info("smtp_starttls=%s", config.smtp_starttls)

    service = EmailService(config)
    run_count = 0
    interval_seconds = max(args.loop_minutes, 0) * 60

    while True:
        run_count += 1
        timestamp = now_iso()
        logger.info("run=%d at %s kind=%s", run_count, timestamp, args.kind)

        if args.kind in {"verification", "both"}:
            send_verification_probe(service, args.to, base_url)
            logger.info("verification email sent to %s", args.to)

        if args.kind in {"alert", "both"}:
            send_alert_probe(service, args.to, base_url)
            logger.info("alert email sent to %s", args.to)

        if interval_seconds <= 0:
            break
        if args.max_runs > 0 and run_count >= args.max_runs:
            break

        logger.info("sleeping %gs before next run", interval_seconds)
        time.sleep(interval_seconds)


if __name__ == "__main__":
    main()
