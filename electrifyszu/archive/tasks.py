"""Collection-task scheduling and lifecycle management.

Tasks declare *which rooms to collect and how often*. Seeds come from:
1. Active subscriptions (priority 0, highest)
2. Manual additions (priority 1)
3. Ranking-sample rooms (priority 2)
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

from electrifyszu.database import get_connection

log = logging.getLogger("electrifyszu.archive.tasks")


class CollectionTaskManager:
    """Register, query, and advance collection tasks."""

    # ── registration ────────────────────────────────────────────────

    def upsert_task(
        self,
        *,
        source: str,
        client: str,
        campus_name: str,
        building_id: str,
        building_name: str,
        room_name: str,
        schedule: str = "daily",
        priority: int = 1,
        reason: str = "manual",
    ) -> int:
        """Add or refresh a task. Returns task PK."""
        conn = get_connection()
        cur = conn.execute(
            "INSERT INTO collection_tasks "
            "(source,client,campus_name,building_id,building_name,"
            " room_name,schedule,priority,reason,added_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(source,client,building_id,room_name) "
            "DO UPDATE SET schedule=excluded.schedule,"
            " priority=excluded.priority,"
            " reason=excluded.reason",
            (source, client, campus_name, building_id, building_name,
             room_name, schedule, priority, reason,
             datetime.now().isoformat()),
        )
        conn.commit()
        return cur.lastrowid

    def enqueue_from_subscriptions(self) -> int:
        """Scan active subscriptions, register missing rooms at prio 0.
        Returns count of newly registered tasks."""
        from electrifyszu.subscription.store import SubscriptionStore

        store = SubscriptionStore(None)
        conn = get_connection()
        count = 0
        for sub in store.list_all():
            if not sub.enabled:
                continue
            row = conn.execute(
                "SELECT 1 FROM collection_tasks "
                "WHERE source=? AND client=? AND building_id=? AND room_name=?",
                ("dorm", sub.client, sub.building_id, sub.room_name),
            ).fetchone()
            if not row:
                conn.execute(
                    "INSERT INTO collection_tasks "
                    "(source,client,campus_name,building_id,building_name,"
                    " room_name,schedule,priority,reason,added_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)",
                    ("dorm", sub.client, sub.campus_name,
                     sub.building_id, sub.building_name, sub.room_name,
                     "daily", 0, "subscriber",
                     datetime.now().isoformat()),
                )
                count += 1
        conn.commit()
        if count:
            log.info("registered %d new tasks from subscriptions", count)
        return count

    # ── query ───────────────────────────────────────────────────────

    def pending_since(self, since_date: str | None = None) -> list[dict]:
        """Rooms whose last_collected predates *since_date* (or never collected)."""
        conn = get_connection()
        sd = since_date or date.today().isoformat()
        rows = conn.execute(
            "SELECT * FROM collection_tasks "
            "WHERE enabled=1 "
            "AND (last_collected IS NULL "
            "OR substr(last_collected,1,10)<?) "
            "ORDER BY priority ASC, building_id, room_name",
            (sd,),
        ).fetchall()
        return [dict(r) for r in rows]

    def pending_today(self) -> list[dict]:
        return self.pending_since(date.today().isoformat())

    # ── advancement ─────────────────────────────────────────────────

    def mark_collected(self, task_id: int, *, ok: bool, status_msg: str = "") -> None:
        conn = get_connection()
        if ok:
            conn.execute(
                "UPDATE collection_tasks "
                "SET last_collected=datetime('now'),"
                " last_status=?, consecutive_failures=0 "
                "WHERE id=?",
                (status_msg or "ok", task_id),
            )
        else:
            conn.execute(
                "UPDATE collection_tasks "
                "SET consecutive_failures=consecutive_failures+1,"
                " last_status=? "
                "WHERE id=?",
                (status_msg or "fail", task_id),
            )
        conn.commit()

    def disable_after_failures(self, threshold: int = 5) -> int:
        """Disable tasks that exceed *threshold* consecutive failures."""
        conn = get_connection()
        cur = conn.execute(
            "UPDATE collection_tasks SET enabled=0 "
            "WHERE consecutive_failures>? AND enabled=1",
            (threshold,),
        )
        n = cur.rowcount
        conn.commit()
        if n:
            log.warning("disabled %d failing tasks", n)
        return n

    # ── bookkeeping ─────────────────────────────────────────────────

    def record_run(
        self,
        *,
        triggered_by: str = "schedule",
        queued: int = 0,
        done: int = 0,
        skipped: int = 0,
        failed: int = 0,
        mappings_hit: int = 0,
        mappings_miss: int = 0,
        duration_sec: float = 0,
        notes: str = "",
    ) -> int:
        conn = get_connection()
        cur = conn.execute(
            "INSERT INTO collection_runs "
            "(started_at,completed_at,duration_sec,"
            " rooms_queued,rooms_done,rooms_skipped,rooms_failed,"
            " mappings_hit,mappings_miss,trigger,notes) "
            "VALUES (datetime('now'),datetime('now'),?,?,?,?,?,?,?,?,?)",
            (duration_sec, queued, done, skipped, failed,
             mappings_hit, mappings_miss, triggered_by, notes),
        )
        conn.commit()
        return cur.lastrowid

    def recent_runs(self, limit: int = 10) -> list[dict]:
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM collection_runs "
            "ORDER BY started_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
