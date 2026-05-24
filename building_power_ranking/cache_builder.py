from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from .cache import (
    DEFAULT_RANKING_CACHE_FILE,
    DEFAULT_ROOMS_PER_FLOOR,
    DEFAULT_SAMPLE_PLAN_FILE,
    build_random_sample_plan,
    cache_with_rankings,
    demo_ranking_from_plan,
    ranking_from_live_result,
    sample_plan_document,
    save_ranking_cache,
    save_sample_plan,
)
from .floor_probe import MONITOR_DIR, load_buildings_file
from .ranking import build_ranking


def main() -> None:
    parser = argparse.ArgumentParser(description="Build cached building power rankings.")
    parser.add_argument("--demo", action="store_true", help="Generate local random demo data without campus network access.")
    parser.add_argument("--all", action="store_true", help="Build rankings for every known building.")
    parser.add_argument("--client", default="", help="Campus client IP.")
    parser.add_argument("--campus-name", default="", help="Campus name for a single building.")
    parser.add_argument("--building-id", default="", help="Building ID for a single building.")
    parser.add_argument("--building-name", default="", help="Building name for a single building.")
    parser.add_argument("--days", type=int, default=30, help="Ranking period in days.")
    parser.add_argument("--min-floor", type=int, default=None)
    parser.add_argument("--max-floor", type=int, default=None)
    parser.add_argument("--rooms-per-floor", type=int, default=DEFAULT_ROOMS_PER_FLOOR)
    parser.add_argument("--room-suffix-start", type=int, default=1)
    parser.add_argument("--room-suffix-end", type=int, default=20)
    parser.add_argument("--seed", type=int, default=20260521)
    parser.add_argument("--cache-file", default=str(DEFAULT_RANKING_CACHE_FILE))
    parser.add_argument("--sample-plan-file", default=str(DEFAULT_SAMPLE_PLAN_FILE))
    args = parser.parse_args()

    buildings = _select_buildings(args)
    generated_at = datetime.now().isoformat(timespec="seconds")
    plans = [
        build_random_sample_plan(
            client=building["client"],
            campus_name=building["campus_name"],
            building_id=building["building_id"],
            building_name=building["building_name"],
            min_floor=args.min_floor,
            max_floor=args.max_floor,
            rooms_per_floor=args.rooms_per_floor,
            room_suffix_start=args.room_suffix_start,
            room_suffix_end=args.room_suffix_end,
            seed=args.seed + index,
        )
        for index, building in enumerate(buildings)
    ]

    if args.demo:
        rankings = [
            demo_ranking_from_plan(plan, days=args.days, seed=args.seed + index, generated_at=generated_at)
            for index, plan in enumerate(plans)
        ]
        source = "demo"
    else:
        rankings = _build_live_rankings(plans, args.days, generated_at)
        source = "cached"

    save_sample_plan(sample_plan_document(plans, source=source, generated_at=generated_at), args.sample_plan_file)
    save_ranking_cache(cache_with_rankings(rankings, source=source, generated_at=generated_at), args.cache_file)
    print(f"Wrote {len(rankings)} ranking(s) to {args.cache_file}")
    print(f"Wrote {len(plans)} sample plan(s) to {args.sample_plan_file}")


def _select_buildings(args: argparse.Namespace) -> list[dict[str, str]]:
    buildings = load_buildings_file()
    if args.all:
        if args.client:
            buildings = [building for building in buildings if building["client"] == args.client]
        return buildings

    if args.client and args.building_id:
        matched = [
            building
            for building in buildings
            if building["client"] == args.client and building["building_id"] == args.building_id
        ]
        if matched:
            return matched

    if args.client and args.building_id and args.building_name:
        return [
            {
                "client": args.client,
                "campus_name": args.campus_name,
                "building_id": args.building_id,
                "building_name": args.building_name,
            }
        ]

    raise SystemExit("Pass --all or provide --client, --building-id, and --building-name.")


def _build_live_rankings(plans: list[dict[str, Any]], days: int, generated_at: str) -> list[dict[str, Any]]:
    sys.path.insert(0, str(MONITOR_DIR))
    from src.api import DormApi
    from src.config import Config
    from src.discover import discover_room_id

    rankings = []
    config = Config.from_env()
    for plan in plans:
        live_result = build_ranking(
            config=config,
            client=plan["client"],
            campus_name=plan["campus_name"],
            building_id=plan["building_id"],
            building_name=plan["building_name"],
            days=days,
            api_factory=DormApi,
            discover_room_id=discover_room_id,
            min_floor=plan["floor_range"]["min"],
            max_floor=plan["floor_range"]["max"],
            sample_rooms=plan["sample_rooms"],
        )
        rankings.append(ranking_from_live_result(live_result, plan, source="cached", generated_at=generated_at))
    return rankings


if __name__ == "__main__":
    main()
