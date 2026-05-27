"""Archive admin endpoints — batch collection, status inspection, history browsing.

Routes (defined in router.py):
    POST   /api/archive/batch    — trigger immediate batch collection
    GET    /api/archive/status   — archive table row counts + recent runs
    GET    /api/archive/history  — consume trending data for one room

All routes require X-Admin-Token authentication.
"""

from __future__ import annotations

import logging
import time
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler

from electrifyszu.config import DormConfig as Config, ApartmentConfig
from electrifyszu.database import ARCHIVE_TABLE_COUNT, get_connection
from electrifyszu.dorm.discover import discover_room_id
from electrifyszu.server.middleware import validate_admin_token
from electrifyszu.server.handlers.types import (
    Handler,
    query_value,
    read_request_data,
    send_error,
    send_json,
)

import electrifyszu.apartment.api as _apt_api

from electrifyszu.archive.collector import PowerCollector
from electrifyszu.archive.snapshot_repo import SnapshotStorage
from electrifyszu.archive.tasks import CollectionTaskManager

logger = logging.getLogger("server")


# ── Admin guard ──────────────────────────────────────────────────────────────

def _require_auth(h: Handler) -> bool:
    if not validate_admin_token(h):
        send_error(
            h, "ADMIN_AUTH_REQUIRED",
            "Provide X-Admin-Token header",
            hint="Set ALERT_ADMIN_TOKEN in .env",
            status=401,
        )
        return False
    return True


# ── POST /api/archive/batch ─────────────────────────────────────────────────

def handle_archive_batch(
    handler: BaseHTTPRequestHandler, query: dict[str, list[str]]
) -> None:
    """Trigger synchronous batch collection of all overdue rooms."""
    if not _require_auth(handler):
        return

    mgr = CollectionTaskManager()
    mgr.enqueue_from_subscriptions()

    tasks = mgr.pending_today()
    if not tasks:
        send_json(handler, {"ok": True, "queued": 0, "done": 0, "failed": 0, "elapsed_s": 0})
        return

    col = PowerCollector()
    t0 = time.monotonic()
    ok = fail = skip = 0

    for tk in tasks:
        try:
            res = col.collect_one_room(
                source=tk["source"],
                client=tk["client"],
                campus_name=tk["campus_name"],
                building_id=tk["building_id"],
                building_name=tk["building_name"],
                room_name=tk["room_name"],
            )
            if res.ok:
                ok += 1
                mgr.mark_collected(tk["id"], ok=True, status_msg="ok")
            else:
                fail += 1
                mgr.mark_collected(tk["id"], ok=False, status_msg=res.error)
        except Exception as exc:
            fail += 1
            mgr.mark_collected(tk["id"], ok=False, status_msg=str(exc)[:80])

    mgr.disable_after_failures(threshold=5)

    elapsed = time.monotonic() - t0
    mgr.record_run(triggered_by="admin-api", queued=len(tasks),
                   done=ok, skipped=skip, failed=fail,
                   duration_sec=elapsed)

    send_json(handler, {
        "ok": True,
        "queued": len(tasks),
        "done": ok,
        "failed": fail,
        "elapsed_s": round(elapsed, 1),
    })


# ── GET /api/archive/status ─────────────────────────────────────────────────

def handle_archive_status(
    handler: BaseHTTPRequestHandler, query: dict[str, list[str]]
) -> None:
    """Report archive table sizes and recent collection runs."""
    if not _require_auth(handler):
        return

    conn = get_connection()

    tables = [
        "room_mappings", "room_snapshots", "daily_consumption",
        "charge_events", "collection_tasks", "collection_runs",
    ]

    counts: dict[str, int] = {}
    for tbl in tables:
        row = conn.execute(f"SELECT COUNT(*) AS c FROM {tbl}").fetchone()
        counts[tbl] = row["c"]

    # Recent runs
    mgr = CollectionTaskManager()
    runs = mgr.recent_runs(limit=5)

    oldest_snapshot: str | None = None
    newest_snapshot: str | None = None
    rs_min = conn.execute(
        "SELECT MIN(captured_at) FROM room_snapshots"
    ).fetchone()[0]
    rs_max = conn.execute(
        "SELECT MAX(captured_at) FROM room_snapshots"
    ).fetchone()[0]
    if rs_min:
        oldest_snapshot = rs_min
    if rs_max:
        newest_snapshot = rs_max

    send_json(handler, {
        "ok": True,
        "tables": counts,
        "table_count": ARCHIVE_TABLE_COUNT,
        "oldest_snapshot": oldest_snapshot,
        "newest_snapshot": newest_snapshot,
        "recent_runs": runs,
    })


# ── GET /api/archive/history ────────────────────────────────────────────────

def handle_archive_history(
    handler: BaseHTTPRequestHandler, query: dict[str, list[str]]
) -> None:
    """Browse historical consumption data for a given room."""
    if not _require_auth(handler):
        return

    source = query_value(query, "source") or "dorm"
    client = query_value(query, "client") or ""
    building_id = query_value(query, "buildingId") or ""
    room_name = query_value(query, "roomName") or ""
    days = int(query_value(query, "days") or "30")

    if not building_id or not room_name:
        send_error(
            handler, "MISSING_PARAMS",
            "buildingId and roomName required",
            status=400,
        )
        return

    # Fill defaults from DormConfig if omitted
    if not client:
        dc = Config.from_env()
        if source == "dorm":
            client = dc.client
        else:
            ac = ApartmentConfig.from_env()
            client = ac.base_url.split(":")[0]  # rough fallback

    ss = SnapshotStorage()

    trend = ss.historical_trend(
        source=source, client=client,
        building_id=building_id, room_name=room_name,
        days_back=days,
    )

    snap = ss.latest_snapshot(
        source=source, client=client,
        building_id=building_id, room_name=room_name,
    )

    charges = ss.recent_charges(
        source=source, client=client,
        building_id=building_id, room_name=room_name,
        limit=10,
    )

    send_json(handler, {
        "ok": True,
        "building_id": building_id,
        "room_name": room_name,
        "trend": trend,
        "latest_snapshot": snap,
        "recent_charges": charges,
    })
