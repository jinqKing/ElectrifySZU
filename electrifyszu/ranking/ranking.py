from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Callable

from electrifyszu.config import MAX_QUERY_DAYS
from electrifyszu.ranking.floor_probe import (
    DEFAULT_FLOOR_RANGE_FILE,
    candidate_floor_range,
    floor_range_key,
    load_floor_ranges,
    probe_building_floor_range,
    upsert_floor_range,
)

RANKING_SUFFIXES = ("01", "05", "10")


def generate_sample_rooms(
    min_floor: int,
    max_floor: int,
    suffixes: tuple[str, ...] = RANKING_SUFFIXES,
) -> list[str]:
    if max_floor < min_floor:
        return []
    return [f"{floor}{suffix}" for floor in range(min_floor, max_floor + 1) for suffix in suffixes]


def mask_room_name(room_name: str) -> str:
    text = str(room_name or "").strip()
    if not text:
        return ""
    if len(text) == 1:
        return "*"
    return text[0] + ("*" * (len(text) - 1))


def build_ranking(
    *,
    config: Any,
    client: str,
    campus_name: str,
    building_id: str,
    building_name: str,
    days: int = 30,
    api_factory: Callable[[Any], Any],
    discover_room_id: Callable[..., str | None],
    floor_range_path: str = str(DEFAULT_FLOOR_RANGE_FILE),
    refresh_floors: bool = False,
    min_floor: int | None = None,
    max_floor: int | None = None,
    sample_rooms: list[str] | None = None,
) -> dict[str, Any]:
    days = min(max(int(days), 1), MAX_QUERY_DAYS)
    config.client = client
    api = api_factory(config)

    floor_record = _resolve_floor_record(
        client=client,
        campus_name=campus_name,
        building_id=building_id,
        building_name=building_name,
        discover_room_id=discover_room_id,
        floor_range_path=floor_range_path,
        refresh_floors=refresh_floors,
        min_floor=min_floor,
        max_floor=max_floor,
    )

    range_min = int(floor_record["ranking_min_floor"])
    range_max = int(floor_record["ranking_max_floor"])
    sample_rooms = sample_rooms or generate_sample_rooms(range_min, range_max)
    ranking: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    for room_name in sample_rooms:
        try:
            room_id = discover_room_id(
                building_id=building_id,
                room_name=room_name,
                client_ip=client,
            )
            if not room_id:
                errors.append({"room_name": room_name, "reason": "room_id_not_found"})
                continue

            status = api.get_status(
                room_id=room_id,
                room_name=room_name,
                days=days,
                threshold=config.low_power_threshold,
            )
            total_used = _number_or_none(status.get("total_used_kwh"))
            if total_used is None:
                errors.append({"room_name": room_name, "reason": "no_usage_records"})
                continue

            ranking.append(
                {
                    "room_name_masked": mask_room_name(room_name),
                    "total_used_kwh": round(total_used, 2),
                    "daily_avg_kwh": _round_or_none(status.get("daily_avg_kwh")),
                    "remaining": _round_or_none(status.get("remaining")),
                    "last_record": status.get("last_record"),
                    "status": status.get("status", "unknown"),
                }
            )
        except Exception as exc:
            errors.append({"room_name": room_name, "reason": str(exc)})

    ranking.sort(key=lambda item: item["total_used_kwh"], reverse=True)
    for index, item in enumerate(ranking, 1):
        item["rank"] = index

    today = datetime.now()
    begin = (today - timedelta(days=days)).strftime("%Y-%m-%d")
    end = today.strftime("%Y-%m-%d")
    return {
        "client": client,
        "campus_name": campus_name,
        "building_id": building_id,
        "building_name": building_name,
        "period": {"begin": begin, "end": end, "days": days},
        "floor_range": {
            "min": range_min,
            "max": range_max,
            "source": floor_record.get("source", "default"),
            "detected_min": floor_record.get("detected_min_floor"),
            "detected_max": floor_record.get("detected_max_floor"),
        },
        "ranking": ranking,
        "stats": {
            "sample_count": len(sample_rooms),
            "ranked_count": len(ranking),
            "skipped_count": len(sample_rooms) - len(ranking),
        },
        "errors": errors[:20],
    }


def _resolve_floor_record(
    *,
    client: str,
    campus_name: str,
    building_id: str,
    building_name: str,
    discover_room_id: Callable[..., str | None],
    floor_range_path: str,
    refresh_floors: bool,
    min_floor: int | None,
    max_floor: int | None,
) -> dict[str, Any]:
    if refresh_floors:
        record = probe_building_floor_range(
            client=client,
            campus_name=campus_name,
            building_id=building_id,
            building_name=building_name,
            discover_room_id=discover_room_id,
            min_floor=min_floor,
            max_floor=max_floor,
        )
        upsert_floor_range(record, floor_range_path)
        return _record_with_ranking_range(record.__dict__)

    records = load_floor_ranges(floor_range_path)
    stored = records.get(floor_range_key(client, building_id))
    if stored:
        return _record_with_ranking_range(stored, min_floor=min_floor, max_floor=max_floor)

    candidate_min, candidate_max, source = candidate_floor_range(building_name, campus_name)
    fallback = {
        "candidate_min_floor": candidate_min,
        "candidate_max_floor": candidate_max,
        "detected_min_floor": None,
        "detected_max_floor": None,
        "source": source,
    }
    return _record_with_ranking_range(fallback, min_floor=min_floor, max_floor=max_floor)


def _record_with_ranking_range(
    record: dict[str, Any],
    *,
    min_floor: int | None = None,
    max_floor: int | None = None,
) -> dict[str, Any]:
    detected_min = record.get("detected_min_floor")
    detected_max = record.get("detected_max_floor")
    candidate_min = int(record.get("candidate_min_floor") or 2)
    candidate_max = int(record.get("candidate_max_floor") or 20)
    ranking_min = int(detected_min or candidate_min)
    ranking_max = int(detected_max or candidate_max)
    if min_floor is not None:
        ranking_min = max(1, int(min_floor))
    if max_floor is not None:
        ranking_max = max(ranking_min, int(max_floor))
    return {**record, "ranking_min_floor": ranking_min, "ranking_max_floor": ranking_max}


def _number_or_none(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def _round_or_none(value: Any) -> float | None:
    number = _number_or_none(value)
    return round(number, 2) if number is not None else None
