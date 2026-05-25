"""SQLite persistence for likes — replaces the old likes.json approach.

Table schema (auto-created on first access)::

    CREATE TABLE IF NOT EXISTS like_ids (
        id         TEXT PRIMARY KEY,
        liked      INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        liked_at   TEXT
    );

- Likes count  → ``SELECT COUNT(*) FROM like_ids WHERE liked = 1``
- Users count  → ``SELECT COUNT(*) FROM like_ids``
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import uuid
from pathlib import Path

_PACKAGE_ROOT = Path(__file__).resolve().parents[2]
_DATA_DIR = Path(os.environ.get("ELECTRIFYSZU_DATA_DIR", str(_PACKAGE_ROOT / "data")))
DB_FILE = _DATA_DIR / "likes.db"

# Old JSON file — checked in two locations for migration:
#   1. Same directory as the DB (Docker volume)
#   2. Package-relative data dir (dev / legacy)
_OLD_JSON_CANDIDATES = [
    _DATA_DIR / "likes.json",
    _PACKAGE_ROOT / "data" / "likes.json",
]

_conn: sqlite3.Connection | None = None
_conn_lock = threading.Lock()
logger = logging.getLogger("likes_db")


# ── Connection management ────────────────────────────────────────────────────

def _get_conn() -> sqlite3.Connection:
    """Lazily initialised, WAL-mode SQLite connection (module-level singleton)."""
    global _conn
    if _conn is not None:
        return _conn
    with _conn_lock:
        if _conn is not None:
            return _conn
        DB_FILE.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(DB_FILE), check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.row_factory = sqlite3.Row
        _create_tables(conn)
        _maybe_migrate_from_json(conn)
        _conn = conn
        logger.info("SQLite database ready: %s", DB_FILE)
        return _conn


# ── Schema ───────────────────────────────────────────────────────────────────

def _create_tables(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS like_ids (
            id         TEXT PRIMARY KEY,
            liked      INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            liked_at   TEXT
        )
    """)
    conn.commit()


# ── Migration from old likes.json ────────────────────────────────────────────

def _maybe_migrate_from_json(conn: sqlite3.Connection) -> None:
    """Import data from old likes.json if present and DB is empty."""
    # Find the JSON file (first candidate that exists)
    json_path = next((p for p in _OLD_JSON_CANDIDATES if p.is_file()), None)
    if json_path is None:
        return

    # Guard: skip if DB already has data
    row = conn.execute("SELECT COUNT(*) FROM like_ids").fetchone()
    if row and row[0] > 0:
        return

    try:
        raw = json_path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to read %s during migration: %s", json_path, exc)
        return

    seen = data.get("seenIds", [])
    liked = set(data.get("likedIds", []))

    if not seen:
        return

    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.executemany(
            "INSERT INTO like_ids (id, liked) VALUES (?, 1)",
            [(uid,) for uid in seen if uid in liked],
        )
        conn.executemany(
            "INSERT INTO like_ids (id, liked) VALUES (?, 0)",
            [(uid,) for uid in seen if uid not in liked],
        )
        conn.commit()
        logger.info(
            "Migrated %d users (%d likes) from %s",
            len(seen), len(liked), json_path,
        )
    except Exception as exc:
        conn.rollback()
        logger.warning("Migration from %s failed: %s", json_path, exc)
        return

    # Rename old file as backup (best-effort)
    try:
        json_path.rename(json_path.with_suffix(".json.migrated"))
    except OSError as exc:
        logger.warning("Could not rename %s after migration: %s", json_path, exc)


# ── Data access functions ────────────────────────────────────────────────────

def stats(conn: sqlite3.Connection) -> tuple[int, int]:
    """Return (like_count, user_count)."""
    row = conn.execute(
        "SELECT COUNT(*) FILTER (WHERE liked = 1) AS likes, COUNT(*) AS users FROM like_ids"
    ).fetchone()
    return (row["likes"], row["users"])


def init_id(conn: sqlite3.Connection) -> str:
    """Generate a new svr-* ID, insert into like_ids, return the ID."""
    new_id = f"svr-{uuid.uuid4().hex[:16]}"
    conn.execute("INSERT INTO like_ids (id) VALUES (?)", (new_id,))
    conn.commit()
    return new_id


def add_like(conn: sqlite3.Connection, user_id: str) -> tuple[int, int]:
    """Mark user_id as liked.  Returns (new_like_count, user_count)."""
    conn.execute(
        "UPDATE like_ids SET liked = 1, liked_at = datetime('now') WHERE id = ?",
        (user_id,),
    )
    conn.commit()
    return stats(conn)


def is_seen(conn: sqlite3.Connection, user_id: str) -> bool:
    row = conn.execute("SELECT 1 FROM like_ids WHERE id = ?", (user_id,)).fetchone()
    return row is not None


def is_liked(conn: sqlite3.Connection, user_id: str) -> bool:
    row = conn.execute("SELECT liked FROM like_ids WHERE id = ?", (user_id,)).fetchone()
    return row is not None and row["liked"] == 1


def get_count(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COUNT(*) FROM like_ids WHERE liked = 1").fetchone()
    return row[0] if row else 0
