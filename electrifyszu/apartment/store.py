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

        # Build trend with estimated_remaining (reverse-engineered from total).
        # When recharges happened inside the query window, subtract their kWh
        # from the back-computed remaining so that recharge amounts don't inflate
        # historical data points.
        recharge_entries: list[tuple[str, float]] = []
        if recharge_records:
            for r in recharge_records:
                t = str(r.get("recharge_time", ""))
                k = to_float(r.get("kwh"))
                if t and k > 0:
                    recharge_entries.append((t[:10], k))
            recharge_entries.sort(key=lambda x: x[0])

        future_kwh = total_used
        future_recharge = sum(k for _, k in recharge_entries)
        ri = 0
        trend: list[dict[str, Any]] = []
        for entry in daily_rows:
            future_kwh -= entry["kwh"]
            # Advance past recharges that occurred on or before this day
            entry_date = entry["date"][:10]
            while ri < len(recharge_entries) and recharge_entries[ri][0] <= entry_date:
                future_recharge -= recharge_entries[ri][1]
                ri += 1
            corrected = (remaining + future_kwh - future_recharge
                         if remaining is not None else None)
            trend.append({
                "date": entry["date"],
                "remaining": round(corrected, 2) if corrected is not None else None,
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
