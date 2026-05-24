#!/usr/bin/env python3
from __future__ import annotations

import argparse

from .api import ApartmentPowerApi
from .buildings import get_building, load_buildings, normalize_building_code
from .config import Config


def known_buildings() -> list[dict[str, object]]:
    return [
        {
            "code": building.code,
            "name": building.name,
            "floors": building.floors,
            "rooms": sum(building.room_counts.values()),
        }
        for building in load_buildings().values()
    ]


def discover_room(building_code: str, room_name: str) -> dict[str, str]:
    building = get_building(building_code)
    return {
        "building_code": building.code,
        "building_name": building.name,
        "floor_code": building.floor_code(room_name),
        "room_code": building.room_code(room_name),
        "room_label": building.room_label(room_name),
    }


def main() -> None:
    parser = argparse.ArgumentParser(prog="apartment-discover")
    parser.add_argument("building_code", nargs="?", help="楼栋编码，例如 01")
    parser.add_argument("room_name", nargs="?", help="房间号，例如 501")
    parser.add_argument("--list", action="store_true", help="列出已整理的楼栋信息")
    parser.add_argument("--online", action="store_true", help="从页面实时读取下拉框")
    parser.add_argument("--floor", default="", help="列出某个楼层的房间，例如 0105")
    args = parser.parse_args()

    api = ApartmentPowerApi(Config.from_env())

    if args.list:
        buildings = api.list_buildings(online=args.online) if args.online else []
        if buildings:
            for building in buildings:
                print(f"{building.value}\t{building.label}")
            return
        for building in known_buildings():
            floors = building["floors"]
            print(
                f"{building['code']}\t{building['name']}\t"
                f"floors={min(floors)}-{max(floors)}\trooms={building['rooms']}"
            )
        return

    if args.building_code and args.floor:
        for room in api.list_rooms(normalize_building_code(args.building_code), args.floor):
            print(f"{room.value}\t{room.label}")
        return

    if args.building_code and args.online:
        for floor in api.list_floors(normalize_building_code(args.building_code)):
            print(f"{floor.value}\t{floor.label}")
        return

    if args.building_code and args.room_name:
        room = discover_room(args.building_code, args.room_name)
        for key, value in room.items():
            print(f"{key}={value}")
        return

    parser.print_help()


if __name__ == "__main__":
    main()
