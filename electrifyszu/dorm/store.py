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
        """SELECT record_time, remaining, total_used, daily_kwh, unit_price
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


# ── Apartment reconstruction ────────────────────────────────────────────────

def reconstruct_apartment_status(
    usage_records: list[dict[str, Any]],
    recharge_records: list[dict[str, Any]],
    room_id: str,
    room_name: str,
    begin: str,
    end: str,
    days: int,
    threshold: float | None,
    fresh_remaining: float | None = None,
) -> dict[str, Any]:
    """Reconstruct a dorm-compatible status dict from apartment-style records.

    Apartment records carry *daily_kwh*/*unit_price* (incremental) instead of
    *remaining*/*total_used* (cumulative).  This function bridges the two shapes
    so the frontend and handler receive the same JSON contract regardless of
    data source.
    """
    result: dict[str, Any] = {
        "room_id": room_id,
        "room_name": room_name,
        "period": {"begin": begin, "end": end, "days": days},
        "records": 0,
        "threshold_kwh": threshold,
        "status": "unknown",
        "recharges": [],
        "trend": [],
    }

    if usage_records:
        remaining = fresh_remaining
        daily_rows: list[dict[str, Any]] = []
        cum = 0.0
        for r in usage_records:
            kwh = _to_float(r.get("daily_kwh") or 0)
            cum += kwh
            daily_rows.append({
                "date": str(r.get("record_time", "")),
                "kwh": kwh,
                "cum": cum,
            })

        total_used = cum
        daily_avg = round(total_used / max(len(daily_rows), 1), 2)

        # Build trend with estimated_remaining (reverse-engineered from total)
        future_kwh = total_used
        trend: list[dict[str, Any]] = []
        for entry in daily_rows:
            future_kwh -= entry["kwh"]
            trend.append({
                "date": entry["date"],
                "remaining": (round(remaining + future_kwh, 2)
                              if remaining is not None else None),
                "daily_used_kwh": round(entry["kwh"], 2),
                "total_used_kwh": round(entry["cum"], 2),
            })

        result["trend"] = trend
        result["records"] = len(daily_rows)
        result.update({
            "remaining": remaining,
            "total_used_kwh": round(total_used, 2),
            "daily_avg_kwh": daily_avg,
            "est_days_left": (round(remaining / daily_avg, 1)
                              if remaining is not None and daily_avg > 0 else None),
            "last_record": daily_rows[-1]["date"] if daily_rows else "",
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


# ── Sftest reconstruction ──────────────────────────────────────────────────

def reconstruct_sftest_status(
    usage_records: list[dict[str, Any]],
    recharge_records: list[dict[str, Any]],
    room_id: str,
    room_name: str,
    begin: str,
    end: str,
    days: int,
    threshold: float | None,
    balance_yuan: float | None = None,
) -> dict[str, Any]:
    """Reconstruct status from sftest-style records.

    Sftest provides both cumulative meter readings (*total_used* / *bmdata*)
    and daily increments (*daily_kwh* / *ydata*).  This is the richest data
    source, so we can compute both dorm-style and apartment-style fields.

    Balance (余额, yuan) is converted to remaining kWh using the fixed
    SZU unit price of 0.6998 元/度.
    """
    UNIT_PRICE = 0.6998

    result: dict[str, Any] = {
        "room_id": room_id,
        "room_name": room_name,
        "period": {"begin": begin, "end": end, "days": days},
        "records": 0,
        "threshold_kwh": threshold,
        "status": "unknown",
        "balance_yuan": balance_yuan,
        "recharges": [],
        "trend": [],
    }

    # Convert balance (元) → remaining (度)
    remaining: float | None = None
    if balance_yuan is not None:
        remaining = round(balance_yuan / UNIT_PRICE, 2)

    if usage_records:
        # Build trend from cumulative total_used (dorm-style) when available;
        # fall back to daily_kwh accumulation
        has_cumulative = any(
            r.get("total_used") is not None and _to_float(r.get("total_used")) > 0
            for r in usage_records
        )

        if has_cumulative:
            # Rich path: cumulative meter readings available
            trend, total_used, daily_avg = _build_trend_from_cumulative(usage_records, remaining)
        else:
            # Lean path: accumulate from daily_kwh
            trend, total_used, daily_avg = _build_trend_from_daily(usage_records, remaining)

        result["trend"] = trend
        result["records"] = len(trend)
        result.update({
            "remaining": remaining,
            "total_used_kwh": round(total_used, 2),
            "daily_avg_kwh": daily_avg,
            "est_days_left": (round(remaining / daily_avg, 1)
                              if remaining is not None and daily_avg > 0 else None),
            "last_record": trend[-1]["date"] if trend else "",
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


def _build_trend_from_cumulative(
    records: list[dict[str, Any]], remaining: float | None,
) -> tuple[list[dict[str, Any]], float, float]:
    """Build trend from cumulative total_used (dorm-style).

    When *remaining* reflects the latest known balance, per-entry remaining
    is back-computed from the cumulative meter readings.
    """
    trend: list[dict[str, Any]] = []
    previous_total: float | None = None

    # Latest cumulative reading for back-computing per-entry remaining
    latest_total = _to_float(records[-1].get("total_used")) if records else 0.0

    for row in records:
        total = _to_float(row.get("total_used"))
        daily_used = 0.0 if previous_total is None else max(total - previous_total, 0.0)
        # Back-compute remaining: if we consumed N kWh since this entry,
        # the remaining at this entry was N kWh higher.
        row_remaining: float | None = None
        if remaining is not None and latest_total > 0:
            row_remaining = round(remaining + (latest_total - total), 2)
        trend.append({
            "date": str(row.get("record_time", "")),
            "remaining": row_remaining,
            "daily_used_kwh": round(daily_used, 2),
            "total_used_kwh": total,
        })
        previous_total = total

    if len(trend) >= 2:
        trend = trend[1:]  # drop baseline row
        total_used = _to_float(records[-1].get("total_used")) - _to_float(records[0].get("total_used"))
        total_used = max(total_used, 0)
    else:
        total_used = 0.0
    daily_avg = round(total_used / max(len(trend), 1), 2)
    return trend, total_used, daily_avg


def _build_trend_from_daily(
    records: list[dict[str, Any]], remaining: float | None,
) -> tuple[list[dict[str, Any]], float, float]:
    """Build trend by accumulating daily_kwh (apartment-style)."""
    trend: list[dict[str, Any]] = []
    cum = 0.0
    for row in records:
        kwh = _to_float(row.get("daily_kwh") or 0)
        cum += kwh
        trend.append({
            "date": str(row.get("record_time", "")),
            "remaining": remaining,
            "daily_used_kwh": round(kwh, 2),
            "total_used_kwh": round(cum, 2),
        })
    total_used = cum
    daily_avg = round(total_used / max(len(trend), 1), 2)
    return trend, total_used, daily_avg


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
