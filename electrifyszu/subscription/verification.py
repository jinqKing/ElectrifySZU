from __future__ import annotations

from pathlib import Path
from typing import Any

from electrifyszu.subscription.email_service import EmailConfig, EmailService
from electrifyszu.subscription.email_templates import verification_content, verification_subject
from electrifyszu.subscription.store import Subscription, SubscriptionSaveResult, SubscriptionStore


def create_pending_subscription(
    store: SubscriptionStore,
    values: dict[str, Any],
    default_threshold: float,
    base_url: str,
    env_path: str | Path,
    request_base_url: str = "",
) -> SubscriptionSaveResult:
    result = store.save(values, default_threshold)
    if result.verification_required:
        send_verification_email(
            result.subscription,
            build_verification_url(
                result.subscription.verification_token,
                base_url=base_url,
                request_base_url=request_base_url,
            ),
            env_path,
        )
    return result


def verify_subscription(
    store: SubscriptionStore,
    token: str,
) -> tuple[str, Subscription | None]:
    return store.verify(token)


def send_verification_email(
    subscription: Subscription,
    confirmation_url: str,
    env_path: str | Path,
) -> None:
    """发送验证邮件。

    异常会向上传播给调用方（server.py），
    由后者返回准确的错误信息给用户。
    """
    EmailService(EmailConfig.from_env(str(env_path))).send_text(
        subscription.email,
        verification_subject(subscription),
        verification_content(subscription, confirmation_url),
    )


def build_verification_url(
    token: str,
    *,
    base_url: str = "",
    request_base_url: str = "",
) -> str:
    base = base_url.strip() or request_base_url.strip()
    if not base:
        base = "http://127.0.0.1:8000"
    return f"{base.rstrip('/')}/api/subscriptions/verify?token={token}"
