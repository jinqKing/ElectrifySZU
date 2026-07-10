"""Apartment (丽湖公寓) reconstruction — normalises stored records into the
unified JSON contract used by the frontend."""

from __future__ import annotations

from typing import Any

from electrifyszu.store import to_float, status_level


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
            kwh = to_float(r.get("daily_kwh") or 0)
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
