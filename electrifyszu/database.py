"""SQLite database for ElectrifySZU — replaces CSV/JSON file storage.

Usage:
    from electrifyszu.database import get_connection

    with get_connection() as conn:
        conn.execute("SELECT ...")

Design:
- Single database file at DATA_DIR / "electrifyszu.db"
- WAL mode for concurrent reads
- Auto-creates tables on first use
- Includes migration helpers for existing CSV/JSON data
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import csv
import secrets
import sqlite3
import threading
from collections.abc import Generator
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger("electrifyszu.db")

# ── Path resolution ─────────────────────────────────────────────────────────

PROJECT_DIR = Path(__file__).resolve().parent
DATA_DIR = PROJECT_DIR.parent / "data"
DB_FILE = DATA_DIR / "electrifyszu.db"
LIKES_LEGACY_FILE = DATA_DIR / "likes.json"
SUBS_LEGACY_FILE = DATA_DIR / "subscriptions.csv"

# Thread-local connections for safe reuse across threads
_local = threading.local()


# ── Connection management ────────────────────────────────────────────────────

SCHEMA_SQL = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS subscriptions (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    email                       TEXT NOT NULL,
    client                      TEXT NOT NULL,
    campus_name                 TEXT NOT NULL,
    building_id                 TEXT NOT NULL,
    building_name               TEXT NOT NULL,
    room_name                   TEXT NOT NULL,
    threshold_kwh               REAL NOT NULL DEFAULT 20.0,
    alert_enabled               INTEGER NOT NULL DEFAULT 1,
    daily_report_enabled        INTEGER NOT NULL DEFAULT 0,
    enabled                     INTEGER NOT NULL DEFAULT 1,
    verified                    INTEGER NOT NULL DEFAULT 0,
    created_at                  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at                  TEXT NOT NULL DEFAULT (datetime('now')),
    verified_at                 TEXT,
    verification_token          TEXT,
    verification_token_expires_at TEXT,
    verification_sent_at        TEXT,
    last_alert_date             TEXT DEFAULT '',
    last_daily_report_date      TEXT DEFAULT '',
    unsubscribe_token           TEXT,
    UNIQUE(email, client, building_id, room_name)
);

CREATE INDEX IF NOT EXISTS idx_subs_alert
    ON subscriptions(alert_enabled, enabled, verified);
CREATE INDEX IF NOT EXISTS idx_subs_daily
    ON subscriptions(daily_report_enabled, enabled, verified);
CREATE INDEX IF NOT EXISTS idx_subs_verify_token
    ON subscriptions(verification_token);
CREATE INDEX IF NOT EXISTS idx_subs_unsub_token
    ON subscriptions(unsubscribe_token);

CREATE TABLE IF NOT EXISTS likes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     TEXT UNIQUE NOT NULL,
    liked       INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ================================================================
-- Power Archive Tables
-- ================================================================

CREATE INDEX IF NOT EXISTS idx_likes_liked ON likes(liked);
CREATE INDEX IF NOT EXISTS idx_likes_user ON likes(user_id);

CREATE TABLE IF NOT EXISTS usage_records (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    client      TEXT NOT NULL,
    room_id     TEXT NOT NULL,
    record_time TEXT NOT NULL,
    remaining   REAL,
    total_used  REAL,
    daily_kwh   REAL,
    unit_price  REAL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(client, room_id, record_time)
);
CREATE INDEX IF NOT EXISTS idx_usage_lookup
    ON usage_records(client, room_id, record_time);

CREATE TABLE IF NOT EXISTS recharge_records (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    client        TEXT NOT NULL,
    room_id       TEXT NOT NULL,
    recharge_time TEXT NOT NULL,
    kwh           REAL,
    yuan          REAL,
    method        TEXT,
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(client, room_id, recharge_time, kwh)
);
CREATE INDEX IF NOT EXISTS idx_recharge_lookup
    ON recharge_records(client, room_id, recharge_time);

CREATE TABLE IF NOT EXISTS room_mapping (
    client         TEXT NOT NULL,
    building_id    TEXT NOT NULL,
    room_name      TEXT NOT NULL,
    room_id        TEXT NOT NULL,
    building_name  TEXT,
    discovered_at  TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(client, building_id, room_name)
);

CREATE TABLE IF NOT EXISTS building_list (
    client        TEXT NOT NULL,
    building_id   TEXT NOT NULL,
    building_name TEXT NOT NULL,
    updated_at    TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(client, building_id)
);

CREATE TABLE IF NOT EXISTS room_mappings (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source          TEXT NOT NULL CHECK(source IN ('dorm','apartment')),
    client          TEXT NOT NULL,
    campus_name     TEXT NOT NULL,
    building_id     TEXT NOT NULL,
    building_name   TEXT NOT NULL,
    room_name       TEXT NOT NULL,
    internal_id     TEXT NOT NULL,
    discovered_at   TEXT NOT NULL,
    refreshed_at    TEXT,
    expire_after    TEXT,
    UNIQUE(source, client, building_id, room_name)
);
CREATE INDEX IF NOT EXISTS idx_rm_lookup
    ON room_mappings(source, client, building_id, room_name);

CREATE TABLE IF NOT EXISTS room_snapshots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source          TEXT NOT NULL CHECK(source IN ('dorm','apartment')),
    client          TEXT NOT NULL,
    campus_name     TEXT NOT NULL,
    building_id     TEXT NOT NULL,
    building_name   TEXT NOT NULL,
    room_name       TEXT NOT NULL,
    remaining       REAL,
    total_used_kwh  REAL,
    daily_avg_kwh   REAL,
    est_days_left   REAL,
    unit_price      REAL,
    price_tier      TEXT,
    status          TEXT,
    captured_at     TEXT NOT NULL,
    period_begin    TEXT,
    period_end      TEXT,
    period_days     INTEGER,
    capture_method  TEXT DEFAULT 'auto',
    api_latency_ms  INTEGER
);
CREATE INDEX IF NOT EXISTS idx_rs_latest
    ON room_snapshots(source, client, building_id, room_name, captured_at DESC);
CREATE INDEX IF NOT EXISTS idx_rs_date
    ON room_snapshots(captured_at);

CREATE TABLE IF NOT EXISTS daily_consumption (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source          TEXT NOT NULL,
    client          TEXT NOT NULL,
    building_id     TEXT NOT NULL,
    room_name       TEXT NOT NULL,
    record_date     TEXT NOT NULL,
    daily_used_kwh  REAL NOT NULL,
    remaining       REAL,
    snapshot_id     INTEGER REFERENCES room_snapshots(id) ON DELETE CASCADE,
    UNIQUE(source, client, building_id, room_name, record_date)
);
CREATE INDEX IF NOT EXISTS idx_dc_query
    ON daily_consumption(source, client, building_id, room_name, record_date DESC);

CREATE TABLE IF NOT EXISTS charge_events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source          TEXT NOT NULL,
    client          TEXT NOT NULL,
    building_id     TEXT NOT NULL,
    room_name       TEXT NOT NULL,
    txn_time        TEXT NOT NULL,
    kwh             REAL,
    yuan            REAL,
    method          TEXT,
    person          TEXT,
    snapshot_id     INTEGER REFERENCES room_snapshots(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_ce_query
    ON charge_events(source, client, building_id, room_name, txn_time DESC);

CREATE TABLE IF NOT EXISTS collection_tasks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source          TEXT NOT NULL CHECK(source IN ('dorm','apartment')),
    client          TEXT NOT NULL,
    campus_name     TEXT NOT NULL,
    building_id     TEXT NOT NULL,
    building_name   TEXT NOT NULL,
    room_name       TEXT NOT NULL,
    schedule        TEXT DEFAULT 'daily',
    priority        INTEGER NOT NULL DEFAULT 1,
    enabled         INTEGER NOT NULL DEFAULT 1,
    reason          TEXT DEFAULT 'manual',
    added_at        TEXT NOT NULL,
    last_collected  TEXT,
    last_status     TEXT,
    consecutive_failures INTEGER DEFAULT 0,
    UNIQUE(source, client, building_id, room_name)
);
CREATE INDEX IF NOT EXISTS idx_ct_ready
    ON collection_tasks(priority, enabled, last_collected);

CREATE TABLE IF NOT EXISTS collection_runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at      TEXT NOT NULL,
    completed_at    TEXT,
    duration_sec    REAL,
    rooms_queued    INTEGER DEFAULT 0,
    rooms_done      INTEGER DEFAULT 0,
    rooms_skipped   INTEGER DEFAULT 0,
    rooms_failed    INTEGER DEFAULT 0,
    mappings_hit    INTEGER DEFAULT 0,
    mappings_miss   INTEGER DEFAULT 0,
    trigger         TEXT DEFAULT 'schedule',
    notes           TEXT
);
CREATE INDEX IF NOT EXISTS idx_cr_time ON collection_runs(started_at DESC);
"""


# Number of archive tables for health-reporting
ARCHIVE_TABLE_COUNT = 6



def get_db_path() -> Path:
    """Return the path to the SQLite database file.

    Override via ELECTRIFYSZU_DB_PATH env var (for testing isolation).
    Priority: 1) env var, 2) thread-local override, 3) default DB_FILE.
    """
    env_path = os.environ.get("ELECTRIFYSZU_DB_PATH")
    if env_path:
        return Path(env_path)
    if hasattr(_local, "forced_db_path") and _local.forced_db_path is not None:
        return _local.forced_db_path
    return DB_FILE


def set_db_path(path: Path | str | None) -> None:
    """Override the DB path for the current thread.

    Used by SubscriptionStore when a legacy CSV path is provided,
    so the SQLite DB is placed alongside the expected data directory.
    Call with None to clear.
    """
    if path is None:
        _local.forced_db_path = None
    else:
        _local.forced_db_path = Path(path)
    # Close stale connection so next get_connection() uses the new path
    close_connection()


def get_connection() -> sqlite3.Connection:
    """Get a thread-local SQLite connection with WAL mode.

    If the DB path changes (e.g. between tests), the old connection
    is closed and a new one is opened.
    """
    db_path = get_db_path()
    if hasattr(_local, "conn") and _local.conn is not None:
        if hasattr(_local, "db_path") and _local.db_path == db_path:
            return _local.conn
        # Path changed — close stale connection
        try:
            _local.conn.close()
        except Exception:
            pass
        _local.conn = None

    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    _local.conn = conn
    _local.db_path = db_path
    return _local.conn


def close_connection() -> None:
    """Close the thread-local connection if open."""
    if hasattr(_local, "conn") and _local.conn is not None:
        try:
            _local.conn.close()
        except Exception:
            pass
        _local.conn = None
        if hasattr(_local, "db_path"):
            _local.db_path = None


def init_db() -> None:
    """Create tables if they don't exist. Safe to call repeatedly."""
    conn = get_connection()
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    logger.info("Database initialized at %s", get_db_path())


# ── Migration helpers ────────────────────────────────────────────────────────

def _legacy_paths() -> tuple[Path, Path]:
    """Return (likes_json_path, subs_csv_path) relative to the current DB.

    Derives legacy paths from the DB directory so that when the DB is
    in a test temp directory, only test-local legacy files are checked.
    """
    db_dir = get_db_path().parent
    return db_dir / "likes.json", db_dir / "subscriptions.csv"


def needs_migration() -> bool:
    """Check if legacy CSV/JSON data exists but DB is empty."""
    likes_legacy, subs_legacy = _legacy_paths()
    if not get_db_path().is_file():
        return likes_legacy.is_file() or subs_legacy.is_file()
    # DB exists — check if it has data
    conn = get_connection()
    sub_count = conn.execute("SELECT COUNT(*) FROM subscriptions").fetchone()[0]
    like_count = conn.execute("SELECT COUNT(*) FROM likes").fetchone()[0]
    return (sub_count == 0 and subs_legacy.is_file()) or (
        like_count == 0 and likes_legacy.is_file()
    )


def migrate_from_legacy() -> dict[str, int]:
    """Migrate data from legacy CSV/JSON files to SQLite.

    Only migrates from files co-located with the current DB directory,
    so test temp directories are isolated from production data.

    Returns a dict of counts: {"subscriptions": N, "likes": N, "errors": N}.
    """
    init_db()
    likes_legacy, subs_legacy = _legacy_paths()
    stats: dict[str, int] = {"subscriptions": 0, "likes": 0, "errors": 0}

    # ── Migrate subscriptions from CSV ──
    if subs_legacy.is_file():
        try:
            count = _migrate_subscriptions_csv(subs_legacy)
            stats["subscriptions"] = count
            logger.info("Migrated %d subscriptions from %s", count, subs_legacy)
        except Exception as exc:
            stats["errors"] += 1
            logger.error("Failed to migrate subscriptions: %s", exc)

    # ── Migrate likes from JSON ──
    if likes_legacy.is_file():
        try:
            count = _migrate_likes_json(likes_legacy)
            stats["likes"] = count
            logger.info("Migrated %d likes from %s", count, likes_legacy)
        except Exception as exc:
            stats["errors"] += 1
            logger.error("Failed to migrate likes: %s", exc)

    return stats


def _migrate_subscriptions_csv(subs_path: Path) -> int:
    """Import subscriptions from legacy CSV into SQLite."""
    from electrifyszu.subscription.store import (
        CSV_FIELDS,
        Subscription,
        _to_bool,
        _to_float,
        _row_verified,
    )

    conn = get_connection()
    count = 0
    with subs_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if not row.get("email", "").strip():
                continue
            try:
                sub = Subscription.from_row(row)
                conn.execute(
                    """INSERT OR IGNORE INTO subscriptions
                        (email, client, campus_name, building_id, building_name,
                         room_name, threshold_kwh, alert_enabled, daily_report_enabled,
                         enabled, verified, created_at, updated_at, verified_at,
                         verification_token, verification_token_expires_at,
                         verification_sent_at, last_alert_date, last_daily_report_date,
                         unsubscribe_token)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        sub.email,
                        sub.client,
                        sub.campus_name,
                        sub.building_id,
                        sub.building_name,
                        sub.room_name,
                        sub.threshold_kwh,
                        1 if sub.alert_enabled else 0,
                        1 if sub.daily_report_enabled else 0,
                        1 if sub.enabled else 0,
                        1 if sub.verified else 0,
                        sub.created_at,
                        sub.updated_at,
                        sub.verified_at or None,
                        sub.verification_token or None,
                        sub.verification_token_expires_at or None,
                        sub.verification_sent_at or None,
                        sub.last_alert_date or "",
                        sub.last_daily_report_date or "",
                        sub.unsubscribe_token or None,
                    ),
                )
                count += 1
            except Exception as exc:
                logger.warning("Skipping invalid subscription row: %s", exc)
    conn.commit()
    return count


def _migrate_likes_json(likes_path: Path) -> int:
    """Import likes from legacy JSON into SQLite."""
    conn = get_connection()
    try:
        data = json.loads(likes_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return 0

    count = 0
    liked_ids: list[str] = data.get("likedIds", [])
    seen_ids: list[str] = data.get("seenIds", [])
    all_ids = list(dict.fromkeys(liked_ids + seen_ids))  # deduplicate, preserve order

    for user_id in all_ids:
        liked = 1 if user_id in liked_ids else 0
        try:
            conn.execute(
                "INSERT OR IGNORE INTO likes (user_id, liked) VALUES (?, ?)",
                (user_id, liked),
            )
            count += 1
        except Exception as exc:
            logger.warning("Skipping invalid like entry %s: %s", user_id, exc)

    conn.commit()
    return count


# ── Auto-init on import ─────────────────────────────────────────────────────

def ensure_db() -> bool:
    """Ensure the database exists with tables. Returns True if migration ran."""
    if not DB_FILE.is_file():
        init_db()
        if needs_migration():
            stats = migrate_from_legacy()
            logger.info("Migration complete: %s", stats)
            return True
        return True
    # DB exists — ensure tables exist
    init_db()
    return False
