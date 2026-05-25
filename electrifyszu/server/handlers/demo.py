"""GET /api/demo-status, posts, stats, version, health, github-stars handlers."""

from __future__ import annotations

import time as _time
from datetime import datetime
from http.server import BaseHTTPRequestHandler
import logging

from electrifyszu.server.handlers.types import send_json

# Optional: ranking data enhances demo with building percentile info.
# In the public server context, the ranking module may not be available.
try:
    from electrifyszu.ranking.cache import cached_ranking_for as _cached_ranking_for, load_ranking_cache as _load_ranking_cache
    cached_ranking_for = _cached_ranking_for
    load_ranking_cache = _load_ranking_cache
    _HAS_RANKING = True
except ImportError:
    _HAS_RANKING = False

    def _empty_ranking(*args: object, **kwargs: object) -> None:
        return None
    cached_ranking_for = _empty_ranking
    load_ranking_cache = _empty_ranking

logger = logging.getLogger("server")

# Cached GitHub star count (refreshed hourly)
_GITHUB_STARS_CACHE: dict[str, object] = {}
GITHUB_REPO_SLUG = "jinqKing/ElectrifySZU"
GITHUB_STARS_TTL = 3600  # seconds


def handle_demo(handler: BaseHTTPRequestHandler) -> None:
    send_json(handler, demo_status())


def handle_version(handler: BaseHTTPRequestHandler) -> None:
    import sys
    from electrifyszu.version import __version__
    send_json(handler, {"ok": True, "version": __version__, "python": sys.version.split()[0]})


def handle_health(handler: BaseHTTPRequestHandler) -> None:
    import sys
    from electrifyszu.version import __version__
    send_json(handler, {
        "ok": True,
        "status": "healthy",
        "version": __version__,
        "python": sys.version.split()[0],
        "timestamp": datetime.now().isoformat(),
    })


def handle_github_stars(handler: BaseHTTPRequestHandler) -> None:
    global _GITHUB_STARS_CACHE
    ts = _GITHUB_STARS_CACHE.get("ts", 0)
    if _time.time() - ts < GITHUB_STARS_TTL:
        send_json(handler, {"ok": True, "stars": _GITHUB_STARS_CACHE["stars"]})
        return
    url = f"https://api.github.com/repos/{GITHUB_REPO_SLUG}"
    try:
        import httpx as _hx
        resp = _hx.get(url, timeout=5)
        stars = resp.json().get("stargazers_count", 0)
    except Exception:
        stars = _GITHUB_STARS_CACHE.get("stars", 0)
    _GITHUB_STARS_CACHE.update(stars=int(stars), ts=_time.time())
    send_json(handler, {"ok": True, "stars": _GITHUB_STARS_CACHE["stars"]})


def demo_status() -> dict[str, object]:
    data = {
        "building_id": "7126",
        "client": "192.168.84.87",
        "campus_name": "粤海",
        "building_name": "风槐斋",
        "room_id": "7322",
        "room_name": "713",
        "period": {"begin": "2026-04-20", "end": "2026-05-20", "days": 30},
        "records": 30,
        "threshold_kwh": 20,
        "status": "low",
        "remaining": 18.6,
        "total_used_kwh": 42.8,
        "daily_avg_kwh": 1.43,
        "est_days_left": 13.0,
        "last_record": "2026-05-20",
        "trend": [
            {"date": "2026-05-14", "remaining": 27.8, "daily_used_kwh": 1.5},
            {"date": "2026-05-15", "remaining": 26.1, "daily_used_kwh": 1.7},
            {"date": "2026-05-16", "remaining": 24.9, "daily_used_kwh": 1.2},
            {"date": "2026-05-17", "remaining": 23.0, "daily_used_kwh": 1.9},
            {"date": "2026-05-18", "remaining": 21.4, "daily_used_kwh": 1.6},
            {"date": "2026-05-19", "remaining": 20.0, "daily_used_kwh": 1.4},
            {"date": "2026-05-20", "remaining": 18.6, "daily_used_kwh": 1.4},
        ],
        "recharges": [
            {"time": "2026-05-08", "kwh": 50, "yuan": 30.5, "method": "微信支付"},
            {"time": "2026-04-19", "kwh": 30, "yuan": 18.3, "method": "支付宝"},
        ],
    }
    ranking_data = cached_ranking_for(load_ranking_cache(), client=data["client"], building_id=data["building_id"])
    if ranking_data and ranking_data.get("ranking") and data.get("total_used_kwh") is not None:
        rows = ranking_data["ranking"]
        below = sum(1 for r in rows if r["total_used_kwh"] < data["total_used_kwh"])
        total = len(rows)
        percentile = round(below / total * 100) if total > 0 else 0
        data["building_percentile"] = percentile
        data["building_rank"] = below + 1
        data["building_rank_total"] = total
    return {"ok": True, "data": data}
