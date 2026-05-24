#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from .api import ApartmentPowerApi
from .config import Config
from .discover import discover_room, known_buildings


def cmd_buildings(args: argparse.Namespace) -> None:
    api = ApartmentPowerApi(Config.from_env())
    if args.online:
        for building in api.list_buildings(online=True):
            print(f"{building.value}\t{building.label}")
        return
    for building in known_buildings():
        floors = building["floors"]
        print(
            f"{building['code']}\t{building['name']}\t"
            f"floors={min(floors)}-{max(floors)}\trooms={building['rooms']}"
        )


def cmd_discover(args: argparse.Namespace) -> None:
    data = discover_room(args.building_code, args.room_name)
    for key, value in data.items():
        print(f"{key}={value}")


def cmd_floors(args: argparse.Namespace) -> None:
    api = ApartmentPowerApi(Config.from_env())
    for floor in api.list_floors(args.building_code):
        print(f"{floor.value}\t{floor.label}")


def cmd_rooms(args: argparse.Namespace) -> None:
    api = ApartmentPowerApi(Config.from_env())
    for room in api.list_rooms(args.building_code, args.floor_code):
        print(f"{room.value}\t{room.label}")


def cmd_usage(args: argparse.Namespace) -> None:
    api = ApartmentPowerApi(Config.from_env())
    result = api.query_usage(
        args.building_code,
        args.room_name,
        begin=args.begin or "",
        end=args.end or "",
        max_pages=args.max_pages,
    )
    print(f"{result.room_label} remaining: {result.remaining} kWh")
    for row in result.records:
        print(
            f"{row.get('日期', '')}\t{row.get('房间名称', '')}\t"
            f"{row.get('用量(度)', '')} kWh\t{row.get('单价(元/度)', '')} yuan/kWh"
        )


def cmd_recharge(args: argparse.Namespace) -> None:
    api = ApartmentPowerApi(Config.from_env())
    result = api.query_recharge(
        args.building_code,
        args.room_name,
        begin=args.begin or "",
        end=args.end or "",
        max_pages=args.max_pages,
    )
    print(f"{result.room_label} remaining: {result.remaining} kWh")
    for row in result.records:
        print(
            f"{row.get('日期', '')}\t{row.get('房间名称', '')}\t"
            f"+{row.get('充值电量(度)', '')} kWh\t{row.get('充值金额(元)', '')} yuan\t"
            f"{row.get('充值人', '')}"
        )


def cmd_status(args: argparse.Namespace) -> None:
    config = Config.from_env()
    api = ApartmentPowerApi(config)
    result = api.get_status(
        args.building_code or config.building_code,
        args.room_name or config.room_name,
        days=args.days,
        threshold=config.low_power_threshold,
    )
    print()
    print("=" * 44)
    print(f"  {result['room_label']} - Status")
    print("=" * 44)
    print(f"  Remaining    : {result.get('remaining', '?')} kWh")
    print(f"  Used (period): {result.get('total_used_kwh', '?')} kWh")
    print(f"  Daily avg    : {result.get('daily_avg_kwh', '?')} kWh/day")
    print(f"  Est. days    : {result.get('est_days_left', '?')} days")
    print(f"  Last record  : {result.get('last_record', '?')}")
    print(f"  Unit price   : {result.get('unit_price', '?')} yuan/kWh")
    if result.get("recharges"):
        print(f"\n  Recharges ({len(result['recharges'])}):")
        for row in result["recharges"][:10]:
            print(
                f"    {row['time']}: +{row['kwh']}kWh = "
                f"{row['yuan']}yuan ({row['person'] or 'unknown'})"
            )
    print("=" * 44)
    print()


def cmd_json(args: argparse.Namespace) -> None:
    config = Config.from_env()
    api = ApartmentPowerApi(config)
    result = api.get_status(
        args.building_code or config.building_code,
        args.room_name or config.room_name,
        days=args.days,
        threshold=config.low_power_threshold,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(prog="apartment-power")
    sub = parser.add_subparsers(dest="cmd")

    p_buildings = sub.add_parser("buildings", help="List known buildings")
    p_buildings.add_argument("--online", action="store_true", help="Read from the live page")
    p_buildings.set_defaults(func=cmd_buildings)

    p_discover = sub.add_parser("discover", help="Resolve room codes")
    p_discover.add_argument("building_code", help="Building code, e.g. 01")
    p_discover.add_argument("room_name", help="Room name, e.g. 501")
    p_discover.set_defaults(func=cmd_discover)

    p_floors = sub.add_parser("floors", help="List floors from the live page")
    p_floors.add_argument("building_code", help="Building code, e.g. 01")
    p_floors.set_defaults(func=cmd_floors)

    p_rooms = sub.add_parser("rooms", help="List rooms from the live page")
    p_rooms.add_argument("building_code", help="Building code, e.g. 01")
    p_rooms.add_argument("floor_code", help="Floor code, e.g. 0105")
    p_rooms.set_defaults(func=cmd_rooms)

    p_usage = sub.add_parser("usage", help="Show usage records")
    p_usage.add_argument("building_code")
    p_usage.add_argument("room_name")
    p_usage.add_argument("--begin", default="", help="YYYY-MM-DD")
    p_usage.add_argument("--end", default="", help="YYYY-MM-DD")
    p_usage.add_argument("--max-pages", type=int, default=None)
    p_usage.set_defaults(func=cmd_usage)

    p_recharge = sub.add_parser("recharge", help="Show recharge records")
    p_recharge.add_argument("building_code")
    p_recharge.add_argument("room_name")
    p_recharge.add_argument("--begin", default="", help="YYYY-MM-DD")
    p_recharge.add_argument("--end", default="", help="YYYY-MM-DD")
    p_recharge.add_argument("--max-pages", type=int, default=None)
    p_recharge.set_defaults(func=cmd_recharge)

    p_status = sub.add_parser("status", help="Show room power status")
    p_status.add_argument("building_code", nargs="?")
    p_status.add_argument("room_name", nargs="?")
    p_status.add_argument("--days", type=int, default=30)
    p_status.set_defaults(func=cmd_status)

    p_json = sub.add_parser("json", help="Output status as JSON")
    p_json.add_argument("building_code", nargs="?")
    p_json.add_argument("room_name", nargs="?")
    p_json.add_argument("--days", type=int, default=30)
    p_json.set_defaults(func=cmd_json)

    args = parser.parse_args()
    if args.cmd is None:
        parser.print_help()
        return
    args.func(args)


if __name__ == "__main__":
    main()
