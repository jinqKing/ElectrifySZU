from __future__ import annotations

from subscription_alerts.email_templates import (
    alert_content,
    daily_report_content,
    verification_content,
    verification_subject,
)
from subscription_alerts.store import Subscription


def sample_subscription() -> Subscription:
    return Subscription(
        email="user@example.com",
        client="192.168.1.1",
        campus_name="Campus A",
        building_id="7126",
        building_name="Building A",
        room_name="713",
        threshold_kwh=20.0,
        alert_enabled=True,
        daily_report_enabled=True,
        enabled=True,
        verified=True,
        created_at="2026-05-22T10:00:00",
        updated_at="2026-05-22T10:00:00",
        verified_at="2026-05-22T10:00:00",
        verification_token="verify-token",
        verification_token_expires_at="2026-05-23T10:00:00",
        verification_sent_at="2026-05-22T10:00:00",
        last_alert_date="",
        last_daily_report_date="",
        unsubscribe_token="unsubscribe-token",
    )


def test_verification_template_contains_url_and_room_details() -> None:
    subscription = sample_subscription()

    subject = verification_subject(subscription)
    content = verification_content(
        subscription,
        "https://power.example.com/api/subscriptions/verify?token=abc",
    )

    assert "ElectrifySZU" in subject
    assert "713" in subject
    assert "https://power.example.com/api/subscriptions/verify?token=abc" in content
    assert "Campus A" in content
    assert "Building A" in content


def test_alert_content_includes_unsubscribe_link_when_base_url_present() -> None:
    content = alert_content(
        sample_subscription(),
        {"remaining": 10, "last_record": "2026-05-22", "status": "low"},
        "https://power.example.com",
    )

    assert "https://power.example.com/api/unsubscribe?token=unsubscribe-token" in content


def test_daily_report_content_handles_empty_trend() -> None:
    content = daily_report_content(
        sample_subscription(),
        {
            "remaining": 18.2,
            "total_used_kwh": 12.5,
            "daily_avg_kwh": 1.3,
            "est_days_left": None,
            "last_record": "2026-05-22",
            "trend": [],
        },
        "https://power.example.com",
    )

    assert "Campus A" in content
    assert "Building A" in content
    assert "https://power.example.com/api/unsubscribe?token=unsubscribe-token" in content
