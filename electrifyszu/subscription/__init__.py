"""Email subscription alerting module."""

from electrifyszu.subscription.alerts import AlertRunner, AlertSettings, shutdown_alert_worker, start_alert_worker
from electrifyszu.subscription.store import Subscription, SubscriptionSaveResult, SubscriptionStore
from electrifyszu.subscription.verification import build_verification_url, send_verification_email, verify_subscription

__all__ = [
    "AlertRunner",
    "AlertSettings",
    "shutdown_alert_worker",
    "start_alert_worker",
    "Subscription",
    "SubscriptionSaveResult",
    "SubscriptionStore",
    "build_verification_url",
    "send_verification_email",
    "verify_subscription",
]
