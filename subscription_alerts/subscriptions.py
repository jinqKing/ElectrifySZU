"""Backward-compatible exports for subscription alert modules."""

from .alerts import AlertRunner, AlertSettings, start_alert_worker
from .store import Subscription, SubscriptionSaveResult, SubscriptionStore
from .verification import build_verification_url, send_verification_email, verify_subscription

__all__ = [
    "AlertRunner",
    "AlertSettings",
    "Subscription",
    "SubscriptionSaveResult",
    "SubscriptionStore",
    "build_verification_url",
    "send_verification_email",
    "start_alert_worker",
    "verify_subscription",
]
