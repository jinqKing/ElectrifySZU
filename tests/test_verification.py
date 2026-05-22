from __future__ import annotations

from pathlib import Path

from subscription_alerts.store import SubscriptionStore
from subscription_alerts.verification import (
    build_verification_url,
    create_pending_subscription,
    send_verification_email,
)


def test_build_verification_url_prefers_base_url() -> None:
    assert (
        build_verification_url(
            "token-123",
            base_url="https://power.example.com/",
            request_base_url="http://127.0.0.1:8000",
        )
        == "https://power.example.com/api/subscriptions/verify?token=token-123"
    )


def test_build_verification_url_falls_back_to_request_base_url() -> None:
    assert (
        build_verification_url(
            "token-123",
            request_base_url="http://localhost:9000",
        )
        == "http://localhost:9000/api/subscriptions/verify?token=token-123"
    )


def test_build_verification_url_uses_default_localhost() -> None:
    assert (
        build_verification_url("token-123")
        == "http://127.0.0.1:8000/api/subscriptions/verify?token=token-123"
    )


def test_create_pending_subscription_sends_email_for_pending(
    temp_csv_path: Path,
    monkeypatch,
) -> None:
    calls: list[tuple[str, str]] = []

    def fake_send(subscription, confirmation_url, env_path):
        calls.append((subscription.email, confirmation_url))

    monkeypatch.setattr(
        "subscription_alerts.verification.send_verification_email",
        fake_send,
    )

    result = create_pending_subscription(
        store=SubscriptionStore(temp_csv_path),
        values={
            "email": "pending@example.com",
            "client": "192.168.1.1",
            "campus_name": "Campus A",
            "building_id": "7126",
            "building_name": "Building A",
            "room_name": "713",
        },
        default_threshold=20,
        base_url="https://power.example.com",
        env_path=temp_csv_path.parent / ".env",
    )

    assert result.verification_required is True
    assert calls == [
        (
            "pending@example.com",
            "https://power.example.com/api/subscriptions/verify"
            f"?token={result.subscription.verification_token}",
        )
    ]


def test_create_pending_subscription_skips_email_for_active(
    temp_csv_path: Path,
    monkeypatch,
) -> None:
    call_count = 0

    def fake_send(subscription, confirmation_url, env_path):
        nonlocal call_count
        call_count += 1

    monkeypatch.setattr(
        "subscription_alerts.verification.send_verification_email",
        fake_send,
    )

    store = SubscriptionStore(temp_csv_path)
    first = create_pending_subscription(
        store=store,
        values={
            "email": "active@example.com",
            "client": "192.168.1.1",
            "campus_name": "Campus A",
            "building_id": "7126",
            "building_name": "Building A",
            "room_name": "713",
        },
        default_threshold=20,
        base_url="https://power.example.com",
        env_path=temp_csv_path.parent / ".env",
    )
    store.verify(first.subscription.verification_token)

    second = create_pending_subscription(
        store=store,
        values={
            "email": "active@example.com",
            "client": "192.168.1.1",
            "campus_name": "Campus A",
            "building_id": "7126",
            "building_name": "Building A",
            "room_name": "713",
        },
        default_threshold=25,
        base_url="https://power.example.com",
        env_path=temp_csv_path.parent / ".env",
    )

    assert second.verification_required is False
    assert second.status == "active"
    assert call_count == 1


def test_send_verification_email_uses_email_service(monkeypatch, temp_csv_path: Path) -> None:
    captured: list[tuple[str, str, str]] = []

    class FakeService:
        def __init__(self, config):
            self.config = config

        def send_text(self, to_email, subject, content):
            captured.append((to_email, subject, content))

    monkeypatch.setattr(
        "subscription_alerts.verification.EmailConfig.from_env",
        lambda env_path: object(),
    )
    monkeypatch.setattr("subscription_alerts.verification.EmailService", FakeService)

    store = SubscriptionStore(temp_csv_path)
    result = store.save(
        {
            "email": "pending@example.com",
            "client": "192.168.1.1",
            "campus_name": "Campus A",
            "building_id": "7126",
            "building_name": "Building A",
            "room_name": "713",
        },
        default_threshold=20,
    )

    send_verification_email(
        result.subscription,
        "https://power.example.com/api/subscriptions/verify?token=abc",
        temp_csv_path.parent / ".env",
    )

    assert captured
    assert captured[0][0] == "pending@example.com"
    assert "ElectrifySZU" in captured[0][1]
    assert "https://power.example.com/api/subscriptions/verify?token=abc" in captured[0][2]
