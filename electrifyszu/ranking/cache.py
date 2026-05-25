from __future__ import annotations

import json
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from electrifyszu.ranking.floor_probe import DEFAULT_FLOOR_RANGE_FILE, candidate_floor_range, floor_range_key, load_floor_ranges
from electrifyszu.ranking.ranking import mask_room_name

DATA_DIR = Path(__file__).resolve().parent / "data"
DEFAULT_RANKING_CACHE_FILE = DATA_DIR / "ranking_cache.json"
DEFAULT_RANKING_CACHE_EXAMPLE_FILE = DATA_DIR / "ranking_cache.example.json"
DEFAULT_SAMPLE_PLAN_FILE = DATA_DIR / "sample_plan.json"
DEFAULT_SAMPLE_PLAN_EXAMPLE_FILE = DATA_DIR / "sample_plan.example.json"
DEFAULT_ROOM_SUFFIX_START = 1
DEFAULT_ROOM_SUFFIX_END = 20
DEFAULT_ROOMS_PER_FLOOR = 3


def load_ranking_cache(
    path: str | Path = DEFAULT_RANKING_CACHE_FILE,
    *,
    fallback_path: str | Path | None = DEFAULT_RANKING_CACHE_EXAMPLE_FILE,
) -> dict[str, Any]:
    target = Path(path)
    if target.is_file():
        return _read_json(target)
    if fallback_path and Path(fallback_path).is_file():
        return _read_json(Path(fallback_path))
    return empty_cache(source="empty")


def save_ranking_cache(cache: dict[str, Any], path: str | Path = DEFAULT_RANKING_CACHE_FILE) -> None:
    _write_json(Path(path), cache)


def load_sample_plan(
    path: str | Path = DEFAULT_SAMPLE_PLAN_FILE,
    *,
    fallback_path: str | Path | None = DEFAULT_SAMPLE_PLAN_EXAMPLE_FILE,
) -> dict[str, Any]:
    target = Path(path)
    if target.is_file():
        return _read_json(target)
    if fallback_path and Path(fallback_path).is_file():
        return _read_json(Path(fallback_path))
    return empty_sample_plan(source="empty")


def save_sample_plan(plan: dict[str, Any], path: str | Path = DEFAULT_SAMPLE_PLAN_FILE) -> None:
    _write_json(Path(path), plan)


def empty_cache(source: str = "cached") -> dict[str, Any]:
    return {
        "version": 1,
        "source": source,
        "generated_at": "",
        "rankings": {},
    }


def empty_sample_plan(source: str = "cached") -> dict[str, Any]:
    return {
        "version": 1,
        "source": source,
        "generated_at": "",
        "plans": {},
    }


def cache_key(client: str, building_id: str) -> str:
    return floor_range_key(client, building_id)


def cached_ranking_for(
    cache: dict[str, Any],
    *,
    client: str,
    building_id: str,
) -> dict[str, Any] | None:
    rankings = cache.get("rankings")
    if not isinstance(rankings, dict):
        return None
    item = rankings.get(cache_key(client, building_id))
    if isinstance(item, dict):
        return {
            **item,
            "source": item.get("source") or cache.get("source") or "cached",
            "cache_generated_at": item.get("cache_generated_at") or cache.get("generated_at", ""),
        }
    return None


def sample_plan_for(
    sample_plan: dict[str, Any],
    *,
    client: str,
    building_id: str,
) -> dict[str, Any] | None:
    plans = sample_plan.get("plans")
    if not isinstance(plans, dict):
        return None
    item = plans.get(cache_key(client, building_id))
    return item if isinstance(item, dict) else None


def build_random_sample_plan(
    *,
    client: str,
    campus_name: str,
    building_id: str,
    building_name: str,
    floor_range_path: str | Path = DEFAULT_FLOOR_RANGE_FILE,
    min_floor: int | None = None,
    max_floor: int | None = None,
    rooms_per_floor: int = DEFAULT_ROOMS_PER_FLOOR,
    room_suffix_start: int = DEFAULT_ROOM_SUFFIX_START,
    room_suffix_end: int = DEFAULT_ROOM_SUFFIX_END,
    seed: int | None = None,
) -> dict[str, Any]:
    rng = random.Random(seed)
    range_min, range_max, source = _floor_range_for_plan(
        client=client,
        campus_name=campus_name,
        building_id=building_id,
        building_name=building_name,
        floor_range_path=floor_range_path,
        min_floor=min_floor,
        max_floor=max_floor,
    )
    suffixes = [f"{value:02d}" for value in range(room_suffix_start, room_suffix_end + 1)]
    rooms_by_floor: dict[str, list[str]] = {}
    sample_rooms: list[str] = []
    sample_size = max(1, min(rooms_per_floor, len(suffixes)))

    for floor in range(range_min, range_max + 1):
        picked = sorted(rng.sample(suffixes, sample_size))
        rooms = [f"{floor}{suffix}" for suffix in picked]
        rooms_by_floor[str(floor)] = rooms
        sample_rooms.extend(rooms)

    return {
        "client": client,
        "campus_name": campus_name,
        "building_id": building_id,
        "building_name": building_name,
        "floor_range": {"min": range_min, "max": range_max, "source": source},
        "room_suffix_range": {"start": room_suffix_start, "end": room_suffix_end},
        "rooms_per_floor": sample_size,
        "sample_rooms": sample_rooms,
        "rooms_by_floor": rooms_by_floor,
        "sample_count": len(sample_rooms),
        "seed": seed,
    }


def demo_ranking_from_plan(
    plan: dict[str, Any],
    *,
    days: int = 30,
    seed: int | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    rng = random.Random(seed)
    generated_at = generated_at or datetime.now().isoformat(timespec="seconds")
    end_date = datetime.fromisoformat(generated_at[:19]).date()
    begin_date = end_date - timedelta(days=max(days, 1))
    rows = []

    for room_name in plan.get("sample_rooms", []):
        daily_avg = rng.uniform(0.3, 6.0)
        total_used = round(daily_avg * days * rng.uniform(0.88, 1.12), 2)
        remaining = round(rng.uniform(6, 95), 1)
        rows.append(
            {
                "room_name_masked": mask_room_name(room_name),
                "total_used_kwh": total_used,
                "daily_avg_kwh": round(total_used / days, 2),
                "remaining": remaining,
                "last_record": end_date.isoformat(),
                "status": "critical" if remaining <= 10 else "low" if remaining <= 20 else "ok",
            }
        )

    rows.sort(key=lambda item: item["total_used_kwh"], reverse=True)
    for index, row in enumerate(rows, 1):
        row["rank"] = index

    return {
        "client": plan["client"],
        "campus_name": plan["campus_name"],
        "building_id": plan["building_id"],
        "building_name": plan["building_name"],
        "period": {"begin": begin_date.isoformat(), "end": end_date.isoformat(), "days": days},
        "floor_range": plan["floor_range"],
        "sample_plan": _public_sample_plan(plan),
        "ranking": rows,
        "stats": {
            "sample_count": len(plan.get("sample_rooms", [])),
            "ranked_count": len(rows),
            "skipped_count": 0,
        },
        "errors": [],
        "source": "demo",
        "cache_generated_at": generated_at,
    }


def ranking_from_live_result(
    live_result: dict[str, Any],
    plan: dict[str, Any],
    *,
    source: str = "cached",
    generated_at: str | None = None,
) -> dict[str, Any]:
    generated_at = generated_at or datetime.now().isoformat(timespec="seconds")
    return {
        **live_result,
        "sample_plan": _public_sample_plan(plan),
        "source": source,
        "cache_generated_at": generated_at,
    }


def cache_with_rankings(rankings: list[dict[str, Any]], *, source: str, generated_at: str) -> dict[str, Any]:
    return {
        "version": 1,
        "source": source,
        "generated_at": generated_at,
        "rankings": {
            cache_key(str(item.get("client", "")), str(item.get("building_id", ""))): item
            for item in rankings
        },
    }


def sample_plan_document(plans: list[dict[str, Any]], *, source: str, generated_at: str) -> dict[str, Any]:
    return {
        "version": 1,
        "source": source,
        "generated_at": generated_at,
        "plans": {
            cache_key(str(item.get("client", "")), str(item.get("building_id", ""))): item
            for item in plans
        },
    }


def _floor_range_for_plan(
    *,
    client: str,
    campus_name: str,
    building_id: str,
    building_name: str,
    floor_range_path: str | Path,
    min_floor: int | None,
    max_floor: int | None,
) -> tuple[int, int, str]:
    stored = load_floor_ranges(floor_range_path).get(floor_range_key(client, building_id))
    if stored:
        range_min = int(stored.get("detected_min_floor") or stored.get("candidate_min_floor") or 2)
        range_max = int(stored.get("detected_max_floor") or stored.get("candidate_max_floor") or 20)
        source = str(stored.get("source") or "floor_range_cache")
    else:
        range_min, range_max, source = candidate_floor_range(building_name, campus_name)
    if min_floor is not None:
        range_min = max(1, int(min_floor))
        source = f"{source}+override"
    if max_floor is not None:
        range_max = max(range_min, int(max_floor))
        source = f"{source}+override"
    return range_min, range_max, source


def _public_sample_plan(plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "floor_range": plan.get("floor_range"),
        "room_suffix_range": plan.get("room_suffix_range"),
        "rooms_per_floor": plan.get("rooms_per_floor"),
        "sample_count": plan.get("sample_count"),
        "seed": plan.get("seed"),
    }


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
