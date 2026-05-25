from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable

PROJECT_DIR = Path(__file__).resolve().parents[1]
MONITOR_DIR = PROJECT_DIR / "room-power-monitor"
DEFAULT_BUILDINGS_FILE = PROJECT_DIR / "room-power-monitor" / "data" / "buildings.txt"
DEFAULT_FLOOR_RANGE_FILE = Path(__file__).resolve().parent / "data" / "building_floor_ranges.json"
DEFAULT_MIN_FLOOR = 2
DEFAULT_MAX_FLOOR = 20
PROBE_SUFFIXES = ("01", "02", "05", "10", "15")


@dataclass
class FloorRangeRecord:
    client: str
    campus_name: str
    building_id: str
    building_name: str
    candidate_min_floor: int
    candidate_max_floor: int
    detected_min_floor: int | None
    detected_max_floor: int | None
    source: str
    sample_valid_rooms: list[str]
    failed_candidates: list[str]
    probed_at: str


def floor_range_key(client: str, building_id: str) -> str:
    return f"{client.strip()}:{building_id.strip()}"


def parse_explicit_floor_range(building_name: str) -> tuple[int, int] | None:
    text = _normalize_digits(building_name)
    match = re.search(r"(\d{1,2})\s*[-~至到]\s*(\d{1,2})(?:\s*(?:楼|层|樓|層))?", text)
    if not match:
        return None

    start = int(match.group(1))
    end = int(match.group(2))
    if start > end:
        start, end = end, start
    if end <= 0:
        return None
    return max(start, 1), min(end, 40)


def candidate_floor_range(
    building_name: str,
    campus_name: str = "",
    *,
    default_min_floor: int = DEFAULT_MIN_FLOOR,
    default_max_floor: int = DEFAULT_MAX_FLOOR,
) -> tuple[int, int, str]:
    explicit = parse_explicit_floor_range(building_name)
    if explicit:
        start, end = explicit
        return max(start, 1), end, "building_name"

    campus = campus_name.strip()
    if campus == "南校区":
        return default_min_floor, min(default_max_floor, 17), "public_reference_south_campus"
    if campus in {"北校区", "粤海", "深大新斋区"}:
        return default_min_floor, min(default_max_floor, 20), "public_reference_yuehai"

    return default_min_floor, default_max_floor, "default"


def probe_building_floor_range(
    *,
    client: str,
    campus_name: str,
    building_id: str,
    building_name: str,
    discover_room_id: Callable[..., str | None],
    suffixes: Iterable[str] = PROBE_SUFFIXES,
    min_floor: int | None = None,
    max_floor: int | None = None,
) -> FloorRangeRecord:
    candidate_min, candidate_max, source = candidate_floor_range(building_name, campus_name)
    if min_floor is not None:
        candidate_min = max(1, int(min_floor))
        source = f"{source}+override"
    if max_floor is not None:
        candidate_max = max(candidate_min, int(max_floor))
        source = f"{source}+override"

    valid_rooms: list[str] = []
    failed_candidates: list[str] = []
    valid_floors: list[int] = []
    suffix_list = tuple(suffixes)

    for floor in range(candidate_min, candidate_max + 1):
        floor_found = False
        for suffix in suffix_list:
            room_name = f"{floor}{suffix}"
            try:
                room_id = discover_room_id(
                    building_id=building_id,
                    room_name=room_name,
                    client_ip=client,
                )
            except Exception as exc:
                failed_candidates.append(f"{room_name}: {exc}")
                continue

            if room_id:
                valid_rooms.append(room_name)
                floor_found = True
            else:
                failed_candidates.append(room_name)

        if floor_found:
            valid_floors.append(floor)

    return FloorRangeRecord(
        client=client,
        campus_name=campus_name,
        building_id=building_id,
        building_name=building_name,
        candidate_min_floor=candidate_min,
        candidate_max_floor=candidate_max,
        detected_min_floor=min(valid_floors) if valid_floors else None,
        detected_max_floor=max(valid_floors) if valid_floors else None,
        source=source,
        sample_valid_rooms=valid_rooms,
        failed_candidates=failed_candidates[:200],
        probed_at=datetime.now().isoformat(timespec="seconds"),
    )


def load_floor_ranges(path: str | Path = DEFAULT_FLOOR_RANGE_FILE) -> dict[str, dict[str, object]]:
    target = Path(path)
    if not target.is_file():
        return {}
    return json.loads(target.read_text(encoding="utf-8"))


def save_floor_ranges(
    records: dict[str, dict[str, object]],
    path: str | Path = DEFAULT_FLOOR_RANGE_FILE,
) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(records, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def upsert_floor_range(
    record: FloorRangeRecord,
    path: str | Path = DEFAULT_FLOOR_RANGE_FILE,
) -> dict[str, dict[str, object]]:
    records = load_floor_ranges(path)
    records[floor_range_key(record.client, record.building_id)] = asdict(record)
    save_floor_ranges(records, path)
    return records


def load_buildings_file(path: str | Path = DEFAULT_BUILDINGS_FILE) -> list[dict[str, str]]:
    buildings: list[dict[str, str]] = []
    campus_pattern = re.compile(r"^##\s+(.+?)\s+client=([^\s]+)")
    building_pattern = re.compile(r"buildingId=\s*(\d+)\s+(.+?)\s*$")
    current_campus = ""
    current_client = ""

    for line in Path(path).read_text(encoding="utf-8").splitlines():
        campus_match = campus_pattern.search(line)
        if campus_match:
            current_campus = campus_match.group(1).strip()
            current_client = campus_match.group(2).strip()
            continue

        building_match = building_pattern.search(line)
        if building_match and current_client:
            buildings.append(
                {
                    "client": current_client,
                    "campus_name": current_campus,
                    "building_id": building_match.group(1),
                    "building_name": building_match.group(2).strip(),
                }
            )
    return buildings


def _normalize_digits(value: str) -> str:
    table = str.maketrans("０１２３４５６７８９－—–", "0123456789---")
    return value.translate(table)


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe dorm building floor ranges.")
    parser.add_argument("--client", default="", help="Only probe one campus client IP.")
    parser.add_argument("--building-id", default="", help="Only probe one building ID.")
    parser.add_argument("--dry-run", action="store_true", help="Print inferred ranges without network probing.")
    args = parser.parse_args()

    if not args.dry_run:
        sys.path.insert(0, str(MONITOR_DIR))
        from src.discover import discover_room_id
    else:
        discover_room_id = None

    records = load_floor_ranges()
    for building in load_buildings_file():
        if args.client and building["client"] != args.client:
            continue
        if args.building_id and building["building_id"] != args.building_id:
            continue

        start, end, source = candidate_floor_range(
            building["building_name"],
            building["campus_name"],
        )
        if args.dry_run:
            print(
                f"{building['campus_name']} {building['building_name']}: "
                f"{start}-{end} ({source})"
            )
            continue

        record = probe_building_floor_range(
            **building,
            discover_room_id=discover_room_id,
        )
        records[floor_range_key(record.client, record.building_id)] = asdict(record)
        save_floor_ranges(records)
        print(
            f"{record.campus_name} {record.building_name}: "
            f"{record.detected_min_floor}-{record.detected_max_floor} "
            f"from {len(record.sample_valid_rooms)} samples"
        )


if __name__ == "__main__":
    main()
