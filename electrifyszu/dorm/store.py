"""Dorm (粤海宿舍) reconstruction — normalises stored records into the unified
JSON contract used by the frontend."""

from __future__ import annotations

from typing import Any

from electrifyszu.store import to_float, status_level


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
        remaining = to_float(last.get("remaining"))
        total_used = max(
            to_float(last.get("total_used")) - to_float(first.get("total_used")),
            0,
        )
        daily_avg = round(total_used / max(len(usage_records) - 1, 1), 2)

        trend: list[dict[str, Any]] = []
        previous_total: float | None = None
        for row in usage_records:
            total = to_float(row.get("total_used"))
            daily_used = 0.0 if previous_total is None else max(total - previous_total, 0.0)
            trend.append({
                "date": str(row.get("record_time", "")),
                "remaining": to_float(row.get("remaining")),
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
            "status": status_level(remaining, threshold),
        })

    if recharge_records:
        result["recharges"] = [
            {
                "time": r.get("recharge_time", ""),
                "kwh": to_float(r.get("kwh")),
                "yuan": to_float(r.get("yuan")),
                "method": str(r.get("method", "")),
            }
            for r in recharge_records
        ]

    return result
