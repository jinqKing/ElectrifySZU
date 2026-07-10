"""Sftest (后勤部新宿舍) reconstruction — normalises stored records into the
unified JSON contract used by the frontend.

Sftest provides both cumulative meter readings (*total_used* / *bmdata*)
and daily increments (*daily_kwh* / *ydata*), making it the richest data
source.  Balance (余额, yuan) is converted to remaining kWh using the
standard SZU unit price of 0.6998 元/度.
"""

from __future__ import annotations

from typing import Any

from electrifyszu.store import to_float, status_level

UNIT_PRICE = 0.6998


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
    """Reconstruct status from sftest-style records."""

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
        # Build trend from cumulative total_used when available;
        # fall back to daily_kwh accumulation
        has_cumulative = any(
            r.get("total_used") is not None and to_float(r.get("total_used")) > 0
            for r in usage_records
        )

        if has_cumulative:
            trend, total_used, daily_avg = _build_trend_from_cumulative(usage_records, remaining)
        else:
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


# ── Trend builders ─────────────────────────────────────────────────────────

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
    latest_total = to_float(records[-1].get("total_used")) if records else 0.0

    for row in records:
        total = to_float(row.get("total_used"))
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
        total_used = to_float(records[-1].get("total_used")) - to_float(records[0].get("total_used"))
        total_used = max(total_used, 0)
    else:
        total_used = 0.0
    daily_avg = round(total_used / max(len(trend), 1), 2)
    return trend, total_used, daily_avg


def _build_trend_from_daily(
    records: list[dict[str, Any]], remaining: float | None,
) -> tuple[list[dict[str, Any]], float, float]:
    """Build trend by accumulating daily_kwh (apartment-style).

    When *remaining* reflects the latest known balance, per-entry remaining
    is back-computed so the trend line decreases rather than staying flat.
    """
    trend: list[dict[str, Any]] = []
    cum = 0.0
    for row in records:
        kwh = to_float(row.get("daily_kwh") or 0)
        cum += kwh
        trend.append({
            "date": str(row.get("record_time", "")),
            "remaining": remaining,   # placeholder — computed below
            "daily_used_kwh": round(kwh, 2),
            "total_used_kwh": round(cum, 2),
        })
    total_used = cum

    # Back-compute per-entry remaining (same logic as _build_trend_from_cumulative)
    for t in trend:
        t["remaining"] = (round(remaining + (total_used - t["total_used_kwh"]), 2)
                          if remaining is not None else None)

    daily_avg = round(total_used / max(len(trend), 1), 2)
    return trend, total_used, daily_avg
