"""Handlers for /api/like/* and /api/stats endpoints — SQLite backend.

Replaces the legacy JSON file storage with the electrifyszu.database SQLite module.
Public handler API is unchanged.
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import threading
import uuid
from http.server import BaseHTTPRequestHandler
from pathlib import Path

from electrifyszu.database import get_connection, ensure_db
from electrifyszu.server.handlers.types import (
    RequestError,
    query_value,
    read_request_data,
    send_error,
    send_json,
    LIKES_FILE,
)

ROOT = Path(__file__).resolve().parents[3]
LIKE_ID_PATTERN = re.compile(r"^svr-[0-9a-f]{16}$")

_likes_lock = threading.Lock()
logger = logging.getLogger("server")


def handle_like_init(handler: BaseHTTPRequestHandler) -> None:
    ensure_db()
    new_id = f"svr-{uuid.uuid4().hex[:16]}"
    conn = get_connection()
    with _likes_lock:
        conn.execute(
            "INSERT OR IGNORE INTO likes (user_id, liked) VALUES (?, 0)",
            (new_id,),
        )
        total = conn.execute("SELECT COUNT(*) FROM likes").fetchone()[0]
        conn.commit()
    send_json(handler, {"ok": True, "id": new_id})


def handle_like(handler: BaseHTTPRequestHandler) -> None:
    ensure_db()
    try:
        body = read_request_data(handler)
    except RequestError:
        return
    user_id = body.get("id", "")
    if not isinstance(user_id, str) or not _is_valid_like_id(user_id):
        send_error(handler, "INVALID_LIKE_ID", "Invalid like id", status=400)
        return

    conn = get_connection()
    with _likes_lock:
        # Check if this user_id exists
        row = conn.execute(
            "SELECT * FROM likes WHERE user_id=?", (user_id,)
        ).fetchone()
        if row is None:
            send_error(handler, "UNKNOWN_LIKE_ID", "Unknown like id", status=400)
            return

        if row["liked"]:
            # Already liked — return current counts
            count = conn.execute("SELECT COUNT(*) FROM likes WHERE liked=1").fetchone()[0]
            total = conn.execute("SELECT COUNT(*) FROM likes").fetchone()[0]
            send_json(handler, {
                "ok": True, "already_liked": True,
                "count": count, "users": total,
            })
            return

        # First time liking
        conn.execute(
            "UPDATE likes SET liked=1 WHERE user_id=?", (user_id,)
        )
        conn.commit()
        count = conn.execute("SELECT COUNT(*) FROM likes WHERE liked=1").fetchone()[0]
        total = conn.execute("SELECT COUNT(*) FROM likes").fetchone()[0]

    logger.info("Like #%d from %s", count, _safe_like_id(user_id))
    send_json(handler, {
        "ok": True, "already_liked": False,
        "count": count, "users": total,
    })


def handle_like_count(handler: BaseHTTPRequestHandler) -> None:
    ensure_db()
    conn = get_connection()
    count = conn.execute("SELECT COUNT(*) FROM likes WHERE liked=1").fetchone()[0]
    send_json(handler, {"ok": True, "count": count})


def handle_like_my(handler: BaseHTTPRequestHandler, query: dict[str, list[str]]) -> None:
    ensure_db()
    user_id = query_value(query, "userId")
    if user_id and not _is_valid_like_id(user_id):
        send_error(handler, "INVALID_LIKE_ID", "Invalid like id", status=400)
        return

    conn = get_connection()
    if user_id:
        row = conn.execute(
            "SELECT liked FROM likes WHERE user_id=?", (user_id,)
        ).fetchone()
        liked = bool(row and row["liked"])
    else:
        liked = False

    send_json(handler, {"ok": True, "data": {"liked": liked}})


def handle_stats(handler: BaseHTTPRequestHandler) -> None:
    ensure_db()
    conn = get_connection()
    likes_count = conn.execute("SELECT COUNT(*) FROM likes WHERE liked=1").fetchone()[0]
    users_count = conn.execute("SELECT COUNT(*) FROM likes").fetchone()[0]
    send_json(handler, {
        "ok": True,
        "data": {"likes": likes_count, "users": users_count},
    })


# ── Legacy JSON persistence (kept for migration / backward compat) ───────────

def _load_likes() -> dict[str, object]:
    """Legacy JSON loader — kept for tests that still use it directly."""
    if not LIKES_FILE.is_file():
        return {"count": 0, "likedIds": [], "seenIds": [], "totalIssued": 0}
    try:
        data = json.loads(LIKES_FILE.read_text(encoding="utf-8"))
        data.setdefault("seenIds", [])
        data.setdefault("totalIssued", 0)
        return data
    except (json.JSONDecodeError, OSError):
        return {"count": 0, "likedIds": [], "seenIds": [], "totalIssued": 0}


def _save_likes(data: dict[str, object]) -> None:
    """Legacy JSON saver — kept for backward compat with existing tests."""
    LIKES_FILE.parent.mkdir(parents=True, exist_ok=True)
    temp_name = ""
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=LIKES_FILE.parent,
            prefix=f".{LIKES_FILE.name}.", suffix=".tmp", delete=False,
        ) as file:
            temp_name = file.name
            json.dump(data, file, ensure_ascii=False)
            file.flush()
            os.fsync(file.fileno())
        Path(temp_name).replace(LIKES_FILE)
    except Exception:
        if temp_name:
            Path(temp_name).unlink(missing_ok=True)
        raise


def _is_valid_like_id(value: str) -> bool:
    return bool(LIKE_ID_PATTERN.fullmatch(value))


def _safe_like_id(value: str) -> str:
    return value[:8] + "..." if len(value) > 8 else "***"
