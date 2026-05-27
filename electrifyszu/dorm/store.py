"""Electricity data persistence — incremental API + SQLite-backed reconstruction.

Replaces repeated, full-range API calls with gap-aware incremental fetching
and permanent structured storage. Once a day's meter reading is stored, it
is never re-fetched.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from electrifyszu.database import get_connection


# ── Gap detection ─────────────────────────────────────────────────────────

def get_usage_gap(
    client: str, room_id: str, begin: str, end: str,
) -> tuple[str | None, str | None]:
    """Return the date range that needs fetching, or (None, None) if fully covered."""
    conn = get_connection()
    row = conn.execute(
        """SELECT MIN(record_time) AS min_t, MAX(record_time) AS max_t
           FROM usage_records
           WHERE client=? AND room_id=? AND record_time >= ?""",
        (client, room_id, begin),
    ).fetchone()

    if row["min_t"] is None:
        return (begin, end)

    today_str = datetime.now().strftime("%Y-%m-%d")
    front_gap = row["min_t"][:10] > begin
    back_gap = row["max_t"][:10] < end and row["max_t"][:10] != today_str

    if front_gap and back_gap:
        return (begin, end)
    if front_gap:
        min_dt = datetime.strptime(row["min_t"][:10], "%Y-%m-%d") - timedelta(days=1)
        return (begin, min_dt.strftime("%Y-%m-%d"))
    if back_gap:
        max_dt = datetime.strptime(row["max_t"][:10], "%Y-%m-%d") + timedelta(days=1)
        return (max_dt.strftime("%Y-%m-%d"), end)
    return (None, None)


# ── Usage records ──────────────────────────────────────────────────────────

def insert_usage_records(
    client: str, room_id: str, records: list[dict[str, Any]],
) -> int:
    """INSERT OR IGNORE. *records* are dicts with keys *record_time*, *remaining*, *total_used*
    and optionally *daily_kwh*, *unit_price* for apartment data."""
    conn = get_connection()
    count = 0
    for r in records:
        cur = conn.execute(
            """INSERT OR IGNORE INTO usage_records
               (client, room_id, record_time, remaining, total_used, daily_kwh, unit_price)
               VALUES (?,?,?,?,?,?,?)""",
            (client, room_id, r["record_time"], r.get("remaining"),
             r.get("total_used"), r.get("daily_kwh"), r.get("unit_price")),
        )
        if cur.rowcount > 0:
            count += 1
    conn.commit()
    return count


def get_usage_records(
    client: str, room_id: str, begin: str, end: str,
) -> list[dict[str, Any]]:
    """Return usage records with *record_time >= begin*, sorted ascending."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT record_time, remaining, total_used
           FROM usage_records
           WHERE client=? AND room_id=? AND record_time >= ?
           ORDER BY record_time ASC""",
        (client, room_id, begin),
    ).fetchall()
    return [dict(r) for r in rows]


# ── Recharge records ───────────────────────────────────────────────────────

def insert_recharge_records(
    client: str, room_id: str, records: list[dict[str, Any]],
) -> int:
    """INSERT OR IGNORE. *records* are dicts with keys *recharge_time*, *kwh*, *yuan*, *method*."""
    conn = get_connection()
    count = 0
    for r in records:
        cur = conn.execute(
            """INSERT OR IGNORE INTO recharge_records
               (client, room_id, recharge_time, kwh, yuan, method)
               VALUES (?,?,?,?,?,?)""",
            (client, room_id, r["recharge_time"], r.get("kwh"), r.get("yuan"), r.get("method", "")),
        )
        if cur.rowcount > 0:
            count += 1
    conn.commit()
    return count


def get_recharge_records(
    client: str, room_id: str,
) -> list[dict[str, Any]]:
    """Return all stored recharge records for a room, newest first."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT recharge_time, kwh, yuan, method
           FROM recharge_records
           WHERE client=? AND room_id=?
           ORDER BY recharge_time DESC""",
        (client, room_id),
    ).fetchall()
    return [dict(r) for r in rows]


def recharge_is_stale(client: str, room_id: str) -> bool:
    """True if no recharge records or the newest is older than 7 days."""
    conn = get_connection()
    row = conn.execute(
        "SELECT MAX(recharge_time) AS latest FROM recharge_records WHERE client=? AND room_id=?",
        (client, room_id),
    ).fetchone()
    if row["latest"] is None:
        return True
    cutoff = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    return row["latest"][:10] < cutoff


# ── Reconstruction ─────────────────────────────────────────────────────────

def reconstruct_dorm_status(
    usage_records: list[dict[str, Any]],
    recharge_records: list[dict[str, Any]],
    room_id: str,
    room_name: str,
    begin: str,
    end: str,
    days: int,
    threshold: float | None,
) -> dict[str, Any]:
    """Reconstruct a ``get_status()`` result dict from stored records.

    Mirrors the computation in ``DormApi.get_status()`` but operates on
    normalised rows from the database instead of raw Excel rows.
    """
    result: dict[str, Any] = {
        "room_id": room_id,
        "room_name": room_name,
        "period": {"begin": begin, "end": end, "days": days},
        "records": max(len(usage_records) - 1, 0),
        "threshold_kwh": threshold,
        "status": "unknown",
        "recharges": [],
        "trend": [],
    }

    if usage_records:
        first = usage_records[0]
        last = usage_records[-1]
        remaining = _to_float(last.get("remaining"))
        total_used = max(
            _to_float(last.get("total_used")) - _to_float(first.get("total_used")),
            0,
        )
        daily_avg = round(total_used / max(len(usage_records) - 1, 1), 2)

        trend: list[dict[str, Any]] = []
        previous_total: float | None = None
        for row in usage_records:
            total = _to_float(row.get("total_used"))
            daily_used = 0.0 if previous_total is None else max(total - previous_total, 0.0)
            trend.append({
                "date": str(row.get("record_time", "")),
                "remaining": _to_float(row.get("remaining")),
                "daily_used_kwh": round(daily_used, 2),
                "total_used_kwh": total,
            })
            previous_total = total

        result["trend"] = trend[1:]  # drop baseline row
        result.update({
            "remaining": remaining,
            "total_used_kwh": round(total_used, 2),
            "daily_avg_kwh": daily_avg,
            "est_days_left": round(remaining / daily_avg, 1) if daily_avg > 0 else None,
            "last_record": str(last.get("record_time", "")),
            "status": _status_level(remaining, threshold),
        })

    if recharge_records:
        result["recharges"] = [
            {
                "time": r.get("recharge_time", ""),
                "kwh": _to_float(r.get("kwh")),
                "yuan": _to_float(r.get("yuan")),
                "method": str(r.get("method", "")),
            }
            for r in recharge_records
        ]

    return result


# ── Helpers ────────────────────────────────────────────────────────────────

def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _status_level(remaining: float | None, threshold: float | None) -> str:
    if remaining is None:
        return "unknown"
    if remaining <= 10:
        return "critical"
    if threshold is not None and remaining <= threshold:
        return "low"
    return "ok"
