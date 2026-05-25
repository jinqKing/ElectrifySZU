"""Handlers for /api/like/* and /api/stats endpoints."""

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
    new_id = f"svr-{uuid.uuid4().hex[:16]}"
    with _likes_lock:
        data = _load_likes()
        seen = data.setdefault("seenIds", [])
        seen.append(new_id)
        data["totalIssued"] = len(seen)
        _save_likes(data)
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
        data = _load_likes()
        seen = data.setdefault("seenIds", [])
        if user_id not in seen:
            send_error(handler, "UNKNOWN_LIKE_ID", "Unknown like id", status=400)
            return
        if user_id in data["likedIds"]:
            send_json(handler, {
                "ok": True, "already_liked": True,
                "count": data["count"], "users": len(seen),
            })
            return
        data["likedIds"].append(user_id)
        data["count"] += 1
        _save_likes(data)
    logger.info("Like #%d from %s", data["count"], _safe_like_id(user_id))
    send_json(handler, {
        "ok": True, "already_liked": False,
        "count": data["count"], "users": data.get("totalIssued", 0),
    })


def handle_like_count(handler: BaseHTTPRequestHandler) -> None:
    with _likes_lock:
        data = _load_likes()
    send_json(handler, {"ok": True, "count": data["count"]})


def handle_like_my(handler: BaseHTTPRequestHandler, query: dict[str, list[str]]) -> None:
    user_id = query_value(query, "userId")
    if user_id and not _is_valid_like_id(user_id):
        send_error(handler, "INVALID_LIKE_ID", "Invalid like id", status=400)
        return
    with _likes_lock:
        data = _load_likes()
        liked = user_id in data["likedIds"]
    send_json(handler, {"ok": True, "data": {"liked": liked}})


def handle_stats(handler: BaseHTTPRequestHandler) -> None:
    with _likes_lock:
        data = _load_likes()
    send_json(handler, {
        "ok": True,
        "data": {"likes": data["count"], "users": data.get("totalIssued", 0)},
    })


# ── Likes data persistence ───────────────────────────────────────────────────

def _load_likes() -> dict[str, object]:
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
