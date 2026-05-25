"""Server route table — maps (method, path) → (module, function)."""

ROUTES: dict[tuple[str, str], tuple[str, str]] = {
    # ── Dorm status ──
    ("GET", "/api/status"):           ("status", "handle_status"),

    # ── Buildings ──
    ("GET", "/api/buildings"):        ("buildings", "handle_buildings"),
    ("GET", "/api/building-ranking"): ("buildings", "handle_building_ranking"),
    ("GET", "/api/apartment/floors"): ("buildings", "handle_apartment_floors"),
    ("GET", "/api/apartment/rooms"):  ("buildings", "handle_apartment_rooms"),

    # ── Demo ──
    ("GET", "/api/demo-status"):      ("demo", "handle_demo"),

    # ── Subscription ──
    ("POST", "/api/subscriptions"):        ("subscription", "handle_subscription_create"),
    ("GET", "/api/subscriptions/verify"):  ("subscription", "handle_subscription_verify"),
    ("GET", "/api/unsubscribe"):           ("subscription", "handle_unsubscribe"),
    ("POST", "/api/alerts/check"):         ("subscription", "handle_alert_check"),

    # ── Likes ──
    ("POST", "/api/like/init"):       ("likes", "handle_like_init"),
    ("POST", "/api/like"):            ("likes", "handle_like"),
    ("GET", "/api/like/count"):       ("likes", "handle_like_count"),
    ("GET", "/api/like/my"):          ("likes", "handle_like_my"),

    # ── Stats / Health ──
    ("GET", "/api/stats"):            ("likes", "handle_stats"),
    ("GET", "/api/version"):          ("demo", "handle_version"),
    ("GET", "/api/health"):           ("demo", "handle_health"),
    ("GET", "/api/github-stars"):     ("demo", "handle_github_stars"),
}
