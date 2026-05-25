"""Handlers for /api/like/* and /api/stats endpoints."""

from __future__ import annotations

import logging
import re
import threading
from http.server import BaseHTTPRequestHandler

from electrifyszu.server.handlers.likes_db import (
    _get_conn,
    add_like,
    get_count,
    init_id,
    is_liked,
    is_seen,
    stats,
)
from electrifyszu.server.handlers.types import (
    RequestError,
    query_value,
    read_request_data,
    send_error,
    send_json,
)

LIKE_ID_PATTERN = re.compile(r"^svr-[0-9a-f]{16}$")

_likes_lock = threading.Lock()
logger = logging.getLogger("server")


def handle_like_init(handler: BaseHTTPRequestHandler) -> None:
    with _likes_lock:
        conn = _get_conn()
        new_id = init_id(conn)
    send_json(handler, {"ok": True, "id": new_id})


def handle_like(handler: BaseHTTPRequestHandler) -> None:
    try:
        body = read_request_data(handler)
    except RequestError:
        return
    user_id = body.get("id", "")
    if not isinstance(user_id, str) or not _is_valid_like_id(user_id):
        send_error(handler, "INVALID_LIKE_ID", "Invalid like id", status=400)
        return
    with _likes_lock:
        conn = _get_conn()
        if not is_seen(conn, user_id):
            send_error(handler, "UNKNOWN_LIKE_ID", "Unknown like id", status=400)
            return
        if is_liked(conn, user_id):
            like_count, user_count = stats(conn)
            send_json(handler, {
                "ok": True, "already_liked": True,
                "count": like_count, "users": user_count,
            })
            return
        like_count, user_count = add_like(conn, user_id)
    logger.info("Like #%d from %s", like_count, _safe_like_id(user_id))
    send_json(handler, {
        "ok": True, "already_liked": False,
        "count": like_count, "users": user_count,
    })


def handle_like_count(handler: BaseHTTPRequestHandler) -> None:
    with _likes_lock:
        conn = _get_conn()
        count = get_count(conn)
    send_json(handler, {"ok": True, "count": count})


def handle_like_my(handler: BaseHTTPRequestHandler, query: dict[str, list[str]]) -> None:
    user_id = query_value(query, "userId")
    if user_id and not _is_valid_like_id(user_id):
        send_error(handler, "INVALID_LIKE_ID", "Invalid like id", status=400)
        return
    with _likes_lock:
        conn = _get_conn()
        liked = is_liked(conn, user_id) if user_id else False
    send_json(handler, {"ok": True, "data": {"liked": liked}})


def handle_stats(handler: BaseHTTPRequestHandler) -> None:
    with _likes_lock:
        conn = _get_conn()
        like_count, user_count = stats(conn)
    send_json(handler, {
        "ok": True,
        "data": {"likes": like_count, "users": user_count},
    })


# ── Helpers ──────────────────────────────────────────────────────────────────

def _is_valid_like_id(value: str) -> bool:
    return bool(LIKE_ID_PATTERN.fullmatch(value))


def _safe_like_id(value: str) -> str:
    return value[:8] + "..." if len(value) > 8 else "***"
