from __future__ import annotations

from .store import SubscriptionStore


def unsubscribe_subscription(store: SubscriptionStore, token: str) -> bool:
    return store.unsubscribe(token)
