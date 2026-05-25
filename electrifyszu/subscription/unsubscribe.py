from __future__ import annotations

from electrifyszu.subscription.store import Subscription, SubscriptionStore


def unsubscribe_subscription(
    store: SubscriptionStore,
    token: str,
) -> tuple[str, Subscription | None]:
    return store.unsubscribe(token)
