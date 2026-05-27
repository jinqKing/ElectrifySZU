#!/usr/bin/env python3
"""Seed room_mappings from active subscriptions.

Scans every active subscription, finds unique (client, building, room) tuples,
forces a campus-network discover for each gap, and populates room_mappings.

Usage:
    python -m electrifyszu.archive.seed_mappings [-v]
"""

import argparse
import logging
import sys
from collections import OrderedDict
from pathlib import Path

from electrifyszu.database import ensure_db
from electrifyszu.logging import setup_logging
from electrifyszu.dorm.discover import discover_room_id
from electrifyszu.archive.mapping_repo import MappingRepository

setup_logging()
log = logging.getLogger("electrifyszu.archive.seed")


def collect_unique_rooms() -> list[dict]:
    from electrifyszu.subscription.store import SubscriptionStore

    store = SubscriptionStore(None)
    seen: OrderedDict[tuple, dict] = OrderedDict()
    for sub in store.list_all():
        if not sub.enabled or not sub.verified:
            continue
        key = (sub.client, sub.building_id, sub.room_name)
        if key not in seen:
            seen[key] = {
                "source": "dorm",
                "client": sub.client,
                "campus_name": sub.campus_name,
                "building_id": sub.building_id,
                "building_name": sub.building_name,
                "room_name": sub.room_name,
            }
    return list(seen.values())


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv) if argv else ap.parse_args()

    ensure_db()
    repo = MappingRepository()

    rooms = collect_unique_rooms()
    if not rooms:
        log.info("No active subscriptions to seed from."); return 0

    log.info("Found %d unique room(s) from subscriptions.", len(rooms))
    gaps = repo.seeds_needed(rooms)
    filled = [r for r in rooms if r not in gaps]
    log.info("Already cached: %d, Need discover: %d", len(filled), len(gaps))

    if not gaps:
        log.info("All rooms already mapped!"); return 0

    ok = bad = 0
    for i, rm in enumerate(gaps, 1):
        lbl = f"{rm['building_name']} {rm['room_name']}"
        if args.verbose:
            log.info("[%d/%d] discovering %s...", i, len(gaps), lbl)
        else:
            print(f"[{i}/{len(gaps)}] {lbl} ...", flush=True, end=" ")

        rid = discover_room_id(
            building_id=rm["building_id"],
            room_name=rm["room_name"],
            client_ip=rm["client"],
            force_rediscover=True,
        )
        if rid:
            repo.put_internal_id(
                source=rm["source"], client=rm["client"],
                campus_name=rm["campus_name"],
                building_id=rm["building_id"],
                building_name=rm["building_name"],
                room_name=rm["room_name"],
                internal_id=rid,
            )
            ok += 1
            if not args.verbose: print(f"+ {rid}")
        else:
            bad += 1
            if not args.verbose: print("! not found")

    log.info("Seeded %d new (+%d cached, +%d fail). Total: %d",
             ok, len(filled), bad, repo.count())
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
