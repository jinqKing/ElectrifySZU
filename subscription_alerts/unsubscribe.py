from __future__ import annotations

from .store import Subscription, SubscriptionStore


def unsubscribe_subscription(
    store: SubscriptionStore,
    token: str,
) -> tuple[str, Subscription | None]:
    return store.unsubscribe(token)
