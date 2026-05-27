"""Snapshot and detail-ingestion layer.

Persists get_status() results into four relational tables and provides
efficient read-back for cache-first serving.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from electrifyszu.database import get_connection

log = logging.getLogger("electrifyszu.archive.snapshots")

_Q_SNAPSHOT_COLS = (
    "source,client,campus_name,building_id,building_name,"
    "room_name,remaining,total_used_kwh,daily_avg_kwh,"
    "est_days_left,unit_price,status,"
    "captured_at,period_begin,period_end,period_days,"
    "capture_method,api_latency_ms"
)


class SnapshotStorage:
    """CRUD for room snapshots and their expanded detail arrays."""

    # ---------------------------------------------------------------
    # Write
    # ---------------------------------------------------------------

    def ingest_status(
        self,
        *,
        source: str,
        client: str,
        campus_name: str,
        building_id: str,
        building_name: str,
        room_name: str,
        status: dict[str, Any],
        captured_at: str | None = None,
        latency_ms: int = 0,
        method: str = "auto",
    ) -> int:
        """Persist one get_status() result. Returns snapshot PK."""
        cap = captured_at or datetime.now().isoformat()
        period = status.get("period") or {}
        conn = get_connection()

        cur = conn.execute(
            f"INSERT INTO room_snapshots({_Q_SNAPSHOT_COLS}) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                source, client, campus_name, building_id, building_name,
                room_name,
                status.get("remaining"),
                status.get("total_used_kwh"),
                status.get("daily_avg_kwh"),
                status.get("est_days_left"),
                status.get("unit_price"),
                status.get("status"),
                cap,
                period.get("begin"),
                period.get("end"),
                period.get("days"),
                method,
                latency_ms,
            ),
        )
        sid = cur.lastrowid

        # Expand trend[]
        for t in status.get("trend", []):
            conn.execute(
                "INSERT OR REPLACE INTO daily_consumption "
                "(source,client,building_id,room_name,"
                " record_date,daily_used_kwh,remaining,snapshot_id) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (source, client, building_id, room_name,
                 t["date"], t["daily_used_kwh"],
                 t.get("remaining"), sid),
            )

        # Expand recharges[]
        for c in status.get("recharges", []):
            conn.execute(
                "INSERT OR REPLACE INTO charge_events "
                "(source,client,building_id,room_name,"
                " txn_time,kwh,yuan,method,person,snapshot_id) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (source, client, building_id, room_name,
                 c.get("time") or c.get("txn_time", ""),
                 c.get("kwh"), c.get("yuan"),
                 c.get("method"), c.get("person"), sid),
            )

        conn.commit()
        log.debug("snapshot %s %s %s -> pk=%d", client, building_id, room_name, sid)
        return sid

    # ---------------------------------------------------------------
    # Read — latest snapshot
    # ---------------------------------------------------------------

    def latest_snapshot(
        self,
        *,
        source: str,
        client: str,
        building_id: str,
        room_name: str,
        max_age_hours: int = 24,
    ) -> dict | None:
        """Most recent snapshot within TTL. None if nothing fresh enough."""
        cut = (datetime.now() - timedelta(hours=max_age_hours)).isoformat()
        conn = get_connection()
        row = conn.execute(
            "SELECT * FROM room_snapshots "
            "WHERE source=? AND client=? AND building_id=? AND room_name=? "
            "AND captured_at>=? "
            "ORDER BY captured_at DESC LIMIT 1",
            (source, client, building_id, room_name, cut),
        ).fetchone()
        return _row_to_dict(row) if row else None

    # ---------------------------------------------------------------
    # Read — historical trend
    # ---------------------------------------------------------------

    def historical_trend(
        self,
        *,
        source: str,
        client: str,
        building_id: str,
        room_name: str,
        days_back: int = 30,
    ) -> list[dict]:
        cut = (datetime.now() - timedelta(days=days_back)).isoformat()
        conn = get_connection()
        rows = conn.execute(
            "SELECT record_date, AVG(daily_used_kwh) AS du, "
            "MAX(remaining) AS rem "
            "FROM daily_consumption "
            "WHERE source=? AND client=? AND building_id=? AND room_name=? "
            "AND record_date>=? "
            "GROUP BY record_date ORDER BY record_date",
            (source, client, building_id, room_name, cut),
        ).fetchall()
        return [{"date": r["record_date"],
                 "daily_used_kwh": r["du"],
                 "remaining": r["rem"]} for r in rows]

    # ---------------------------------------------------------------
    # Read — charges
    # ---------------------------------------------------------------

    def recent_charges(
        self,
        *,
        source: str,
        client: str,
        building_id: str,
        room_name: str,
        limit: int = 20,
    ) -> list[dict]:
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM charge_events "
            "WHERE source=? AND client=? AND building_id=? AND room_name=? "
            "ORDER BY txn_time DESC LIMIT ?",
            (source, client, building_id, room_name, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    # ---------------------------------------------------------------
    # Maintenance
    # ---------------------------------------------------------------

    def prune_before(
        self,
        *,
        cutoff: str,
        dry_run: bool = False,
    ) -> int:
        """Delete snapshots older than *cutoff* ISO-string.
        Cascade deletes cover child tables via FK ON DELETE CASCADE."""
        conn = get_connection()
        cur = conn.execute(
            "SELECT COUNT(*) FROM room_snapshots WHERE captured_at<?",
            (cutoff,),
        )
        n = cur.fetchone()[0]
        if not dry_run:
            conn.execute("DELETE FROM room_snapshots WHERE captured_at<?", (cutoff,))
            conn.commit()
        log.info("prune_before(%s): %d rows %s", cutoff, n,
                 "(dry-run)" if dry_run else "deleted")
        return n


# ---------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------

_SNAP_FLATS = (
    "source","client","campus_name","building_id","building_name",
    "room_name","remaining","total_used_kwh","daily_avg_kwh",
    "est_days_left","unit_price","price_tier","status",
    "captured_at","period_begin","period_end","period_days",
    "capture_method","api_latency_ms",
)


def _row_to_dict(row) -> dict | None:
    if row is None:
        return None
    d = {col: row[col] for col in _SNAP_FLATS}
    d["period"] = {"begin": d.pop("period_begin"),
                   "end": d.pop("period_end"),
                   "days": d.pop("period_days")}
    return d
