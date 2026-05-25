#!/usr/bin/env python3
"""
宿舍不断电 — 命令行工具

用法:
  python -m src.cli status [room_name]
  python -m src.cli usage [room_name] [--begin DATE] [--end DATE]
  python -m src.cli json [room_name]
"""

import argparse
import json

from .config import Config
from .api import DormApi, parse_excel


def cmd_status(args):
    cfg = Config.from_env()
    api = DormApi(cfg)
    rid = args.room_id or cfg.room_id
    rname = args.room_name or cfg.room_name
    result = api.get_status(rid, rname)

    print()
    print("=" * 40)
    print(f"  Room {result['room_name']} - Status")
    print("=" * 40)
    print(f"  Remaining    : {result.get('remaining', '?')} kWh")
    print(f"  Used (period): {result.get('total_used_kwh', '?')} kWh")
    print(f"  Daily avg    : {result.get('daily_avg_kwh', '?')} kWh/day")
    print(f"  Est. days    : {result.get('est_days_left', '?')} days")
    print(f"  Last record  : {result.get('last_record', '?')}")
    if result.get("recharges"):
        print(f"\n  Recharges ({len(result['recharges'])}):")
        for r in result["recharges"]:
            unit = (f"({r['yuan']/r['kwh']:.2f} yuan/kWh)"
                    if r["kwh"] > 0 and r["yuan"] > 0 else "(free)")
            print(f"    {r['time']}: +{r['kwh']}kWh = {r['yuan']}yuan {unit}")
    print("=" * 40)
    print()


def cmd_usage(args):
    cfg = Config.from_env()
    api = DormApi(cfg)
    rid = args.room_id or cfg.room_id
    rname = args.room_name or cfg.room_name
    data = api.get_usage(rid, rname,
        begin=args.begin or "",
        end=args.end or "",
    )
    records = parse_excel(data)
    if not records:
        print("No records found.")
        return
    for r in records:
        keys = list(r.keys())
        print(f"{r[keys[5]]}\t{r[keys[2]]} kWh\t{r[keys[3]]} kWh used")


def cmd_json(args):
    cfg = Config.from_env()
    api = DormApi(cfg)
    rid = args.room_id or cfg.room_id
    rname = args.room_name or cfg.room_name
    result = api.get_status(rid, rname)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(prog="dorm-power")
    sub = parser.add_subparsers(dest="cmd")

    p_status = sub.add_parser("status", help="Show room power status")
    p_status.add_argument("room_name", nargs="?", default="", help="Room name")
    p_status.add_argument("--room-id", default="", help="Room ID (optional)")
    p_status.set_defaults(func=cmd_status)

    p_usage = sub.add_parser("usage", help="Show daily usage records")
    p_usage.add_argument("room_name", nargs="?", default="", help="Room name")
    p_usage.add_argument("--room-id", default="", help="Room ID (optional)")
    p_usage.add_argument("--begin", default="", help="Start date (YYYY-MM-DD)")
    p_usage.add_argument("--end", default="", help="End date (YYYY-MM-DD)")
    p_usage.set_defaults(func=cmd_usage)

    p_json = sub.add_parser("json", help="Output JSON for automation")
    p_json.add_argument("room_name", nargs="?", default="", help="Room name")
    p_json.add_argument("--room-id", default="", help="Room ID (optional)")
    p_json.set_defaults(func=cmd_json)

    args = parser.parse_args()
    if args.cmd is None:
        parser.print_help()
    else:
        args.func(args)


if __name__ == "__main__":
    main()
