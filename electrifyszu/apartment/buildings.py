from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "apartment_buildings.txt"


@dataclass(frozen=True)
class Building:
    code: str
    name: str
    room_counts: dict[int, int]

    @property
    def floors(self) -> list[int]:
        return sorted(self.room_counts)

    def floor_label(self, floor: int) -> str:
        return f"{self.name}{floor}层"

    def room_code(self, room_name: str) -> str:
        floor, ordinal = split_room_name(room_name)
        max_room = self.room_counts.get(floor)
        if max_room is None:
            floor_range = _range_label(self.floors)
            raise ValueError(f"{self.name} 没有 {floor} 层；可用楼层为 {floor_range}。")
        if ordinal < 1 or ordinal > max_room:
            raise ValueError(
                f"{self.name}{floor} 层房间序号应在 01-{max_room:02d}，当前为 {ordinal:02d}。"
            )
        return f"{self.code}{floor:02d}{ordinal:02d}"

    def floor_code(self, room_name: str) -> str:
        floor, _ = split_room_name(room_name)
        if floor not in self.room_counts:
            floor_range = _range_label(self.floors)
            raise ValueError(f"{self.name} 没有 {floor} 层；可用楼层为 {floor_range}。")
        return f"{self.code}{floor:02d}"

    def room_label(self, room_name: str) -> str:
        floor, ordinal = split_room_name(room_name)
        return f"{self.name}{floor}{ordinal:02d}"

    def iter_rooms(self) -> Iterable[tuple[str, str]]:
        for floor in self.floors:
            for ordinal in range(1, self.room_counts[floor] + 1):
                yield (
                    f"{self.code}{floor:02d}{ordinal:02d}",
                    f"{self.name}{floor}{ordinal:02d}",
                )


def load_buildings(path: Path = DATA_FILE) -> dict[str, Building]:
    buildings: dict[str, Building] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        fields = dict(re.findall(r"(\w+)=([^\s]+)", line))
        code = fields.get("building", "").strip()
        name = fields.get("name", "").strip()
        floors = fields.get("floors", "").strip()
        if not code or not name or not floors:
            continue
        buildings[code] = Building(
            code=code,
            name=name,
            room_counts=_parse_floor_spec(
                floors,
                rooms_per_floor=fields.get("rooms_per_floor"),
            ),
        )
    return buildings


def get_building(building_code: str) -> Building:
    buildings = load_buildings()
    code = normalize_building_code(building_code)
    if code not in buildings:
        known = ", ".join(f"{item.code}({item.name})" for item in buildings.values())
        raise ValueError(f"未知楼栋编码 {building_code}；已知楼栋：{known}")
    return buildings[code]


def normalize_building_code(value: str) -> str:
    value = str(value).strip()
    if value.isdigit() and len(value) == 1:
        return f"0{value}"
    return value


def split_room_name(room_name: str) -> tuple[int, int]:
    text = str(room_name).strip()
    match = re.search(r"(\d{3,4})\s*$", text)
    if not match:
        raise ValueError(f"无法从房间号 {room_name!r} 解析楼层和房间序号。")
    digits = match.group(1)
    floor = int(digits[:-2])
    ordinal = int(digits[-2:])
    return floor, ordinal


def _parse_floor_spec(spec: str, rooms_per_floor: str | None) -> dict[int, int]:
    if rooms_per_floor:
        count = int(rooms_per_floor)
        start_text, _, end_text = spec.partition("-")
        start = int(start_text)
        end = int(end_text)
        return {floor: count for floor in range(start, end + 1)}

    counts: dict[int, int] = {}
    for part in spec.split(","):
        floor_text, _, count_text = part.partition(":")
        if floor_text and count_text:
            counts[int(floor_text)] = int(count_text)
    return counts


def _range_label(values: list[int]) -> str:
    if not values:
        return "空"
    ranges: list[str] = []
    start = previous = values[0]
    for value in values[1:]:
        if value == previous + 1:
            previous = value
            continue
        ranges.append(f"{start}-{previous}" if start != previous else str(start))
        start = previous = value
    ranges.append(f"{start}-{previous}" if start != previous else str(start))
    return ", ".join(ranges)
