#!/usr/bin/env python3
"""Interactive CLI for the power archive subsystem.

Commands:
    collect   — collect one room now
    batch     — collect all overdue tasks
    backfill  — deep history pull for one room
    status    — show archive statistics
    mappings  — manage room-ID mappings
    history   — view archived trend for a room

Usage:
    python -m electrifyszu.archive.cli collect --building 7126 --room 713
    python -m electrifyszu.archive.cli batch
    python -m electrifyszu.archive.cli backfill --building 7126 --room 713 --days 120
    python -m electrifyszu.archive.cli status
    python -m electrifyszu.archive.cli mappings --show
    python -m electrifyszu.archive.cli history --building 7126 --room 713
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import date, datetime

from electrifyszu.database import ARCHIVE_TABLE_COUNT, ensure_db, get_connection
from electrifyszu.logging import setup_logging
from electrifyszu.archive.collector import PowerCollector
from electrifyszu.archive.mapping_repo import MappingRepository
from electrifyszu.archive.snapshot_repo import SnapshotStorage
from electrifyszu.archive.tasks import CollectionTaskManager

setup_logging()
log = logging.getLogger("electrifyszu.archive.cli")


# ── common arg builders ──────────────────────────────────────────────

def _common_parser(add_help: bool = True) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="archive-cli", add_help=add_help)
    p.add_argument("--source", choices=["dorm", "apartment"], default="dorm")
    p.add_argument("--client", default="", help="Campus client IP")
    p.add_argument("--campus-name", default="", dest="campus_name")
    p.add_argument("--building", default="", dest="building_id")
    p.add_argument("--building-name", default="", dest="building_name")
    p.add_argument("--room", default="", dest="room_name")
    return p


def _resolve_defaults(args: argparse.Namespace) -> None:
    """Fill blanks from .env DormConfig."""
    from electrifyszu.config import DormConfig as DC
    cfg = DC.from_env()
    if not args.client:
        args.client = cfg.client
    if not args.campus_name:
        args.campus_name = cfg.campus_name
    if not args.building_name:
        args.building_name = cfg.building_name


# ── subcommands ──────────────────────────────────────────────────────

def cmd_collect(args: argparse.Namespace) -> int:
    _resolve_defaults(args)
    if not args.building_id or not args.room_name:
        print("ERROR: --building and --room required for collect", file=sys.stderr)
        return 1

    col = PowerCollector()
    t0 = time.monotonic()
    res = col.collect_one_room(
        source=args.source,
        client=args.client,
        campus_name=args.campus_name,
        building_id=args.building_id,
        building_name=args.building_name,
        room_name=args.room_name,
    )
    el = time.monotonic() - t0

    if res.ok:
        print(f"OK  {args.building_name} {args.room_name}  "
              f"snap=#{res.snapshot_id}  {el:.1f}s")
    else:
        print(f"FAIL {args.building_name} {args.room_name}  {res.error}")
        return 1
    return 0


def cmd_batch(args: argparse.Namespace) -> int:
    mgr = CollectionTaskManager()
    mgr.enqueue_from_subscriptions()

    tasks = mgr.pending_today()
    if not tasks:
        print("No overdue tasks — all caught up.")
        return 0

    print(f"Queuing {len(tasks)} overdue room(s)…")

    col = PowerCollector()
    t0 = time.monotonic()
    ok = fail = skip = miss = hit_cnt = 0

    repo = MappingRepository()

    for tk in tasks:
        lk = (tk["source"], tk["client"], tk["building_id"], tk["room_name"])
        if repo.get_internal_id(source=lk[0], client=lk[1],
                                 building_id=lk[2], room_name=lk[3]):
            hit_cnt += 1
        else:
            miss += 1

        lab = f"{tk['building_name']} {tk['room_name']}"
        print(f"  [{hit_cnt+miss}] {lab}…", end=" ", flush=True)

        try:
            res = col.collect_one_room(
                source=tk["source"],
                client=tk["client"],
                campus_name=tk["campus_name"],
                building_id=tk["building_id"],
                building_name=tk["building_name"],
                room_name=tk["room_name"],
            )
            if res.ok:
                ok += 1
                mgr.mark_collected(tk["id"], ok=True, status_msg="ok")
                print(f"+ #{res.snapshot_id}")
            else:
                fail += 1
                mgr.mark_collected(tk["id"], ok=False, status_msg=res.error)
                print(f"! {res.error[:40]}")
        except Exception as ex:
            fail += 1
            mgr.mark_collected(tk["id"], ok=False, status_msg=str(ex)[:80])
            msg = str(ex)[:40]
            print(f"E {msg}")

    mgr.disable_after_failures(threshold=5)

    dur = time.monotonic() - t0
    mgr.record_run(triggered_by="cli-batch", queued=len(tasks),
                   done=ok, skipped=skip, failed=fail,
                   mappings_hit=hit_cnt, mappings_miss=miss,
                   duration_sec=dur)

    print(f"\nBatch done: {ok} ok, {fail} fail, {dur:.1f}s")
    return 0 if fail == 0 else 1


def cmd_backfill(args: argparse.Namespace) -> int:
    _resolve_defaults(args)
    if not args.building_id or not args.room_name:
        print("ERROR: --building and --room required", file=sys.stderr)
        return 1

    days = int(getattr(args, "days", 120))
    col = PowerCollector()
    results = col.backfill_room(
        source=args.source,
        client=args.client,
        campus_name=args.campus_name,
        building_id=args.building_id,
        building_name=args.building_name,
        room_name=args.room_name,
        days=days,
    )

    for r in results:
        if r.ok:
            print(f"OK  snap=#{r.snapshot_id}  {r.latency_ms}ms")
        else:
            print(f"FAIL {r.error}")
    return 0


def cmd_status(_args: argparse.Namespace) -> int:
    conn = get_connection()

    labels = [
        ("room_mappings", "Mappings"),
        ("room_snapshots", "Snapshots"),
        ("daily_consumption", "Daily readings"),
        ("charge_events", "Charges"),
        ("collection_tasks", "Active tasks"),
        ("collection_runs", "Runs logged"),
    ]

    print(f"{'Table':.<28} {'Rows':>8}")
    print("-" * 38)
    for tbl, lbl in labels:
        row = conn.execute(f"SELECT COUNT(*) AS c FROM {tbl}").fetchone()
        print(f"{lbl:<28} {row['c']:>8,}")

    # Recent runs
    mgr = CollectionTaskManager()
    runs = mgr.recent_runs(limit=3)
    if runs:
        print(f"\nRecent runs:")
        for rn in runs:
            ts = rn.get("started_at", "?")
            print(f"  {ts}  {rn.get('trigger','')}  "
                  f"d={rn.get('rooms_done',0)}  f={rn.get('rooms_failed',0)}  "
                  f"{rn.get('duration_sec',0):.1f}s")

    return 0


def cmd_mappings(args: argparse.Namespace) -> int:
    repo = MappingRepository()

    if getattr(args, "show", False):
        bl = getattr(args, "building", None)
        items = repo.listing(source=args.source, building_id=bl)
        if not items:
            print("(empty)")
            return 0
        print(f"{'Src':<4} {'Client':<18} {'Building':<8} {'Room':<6} "
              f"{'IntID':<8} {'Expire'}")
        print("-" * 72)
        for m in items:
            print(f"{m['source']:<4} {m['client']:<18} {m['building_id']:<8} "
                  f"{m['room_name']:<6} {m['internal_id']:<8} {m.get('expire_after','∞')}")
        print(f"\nTotal: {len(items)}")
        return 0

    if getattr(args, "purge", False):
        n = repo.purge_expired()
        print(f"Purged {n} expired mapping(s)")
        return 0

    print("ERROR: specify --show or --purge", file=sys.stderr)
    return 1


def cmd_history(args: argparse.Namespace) -> int:
    _resolve_defaults(args)
    if not args.building_id or not args.room_name:
        print("ERROR: --building and --room required", file=sys.stderr)
        return 1

    days = int(getattr(args, "history_days", 30))
    ss = SnapshotStorage()

    trend = ss.historical_trend(
        source=args.source,
        client=args.client,
        building_id=args.building_id,
        room_name=args.room_name,
        days_back=days,
    )

    if not trend:
        print("No archived data found.")
        return 0

    print(f"Trend for {args.building_name} {args.room_name} "
          f"(last {days} days):")
    print(f"{'Date':<12} {'Used kWh':>10} {'Remaining':>10}")
    print("-" * 34)
    for t in trend:
        rem = f"{t['remaining']:.1f}" if t['remaining'] is not None else "-"
        print(f"{t['date']:<12} {t['daily_used_kwh']:>10.2f} {rem:>10}")

    # Latest snapshot
    snap = ss.latest_snapshot(
        source=args.source, client=args.client,
        building_id=args.building_id, room_name=args.room_name,
    )
    if snap:
        print(f"\nLatest snapshot ({snap['captured_at']}):")
        print(f"  remaining    = {snap['remaining']}")
        print(f"  total_used   = {snap['total_used_kwh']}")
        print(f"  daily_avg    = {snap['daily_avg_kwh']}")
        print(f"  est_days     = {snap['est_days_left']}")
        print(f"  status       = {snap['status']}")

    # Charges
    charges = ss.recent_charges(
        source=args.source, client=args.client,
        building_id=args.building_id, room_name=args.room_name,
    )
    if charges:
        print(f"\nRecent charges ({len(charges)}):")
        for c in charges[:5]:
            print(f"  {c.get('txn_time','-')}  ¥{c.get('yuan',0)}  "
                  f"{c.get('kwh',0)}kWh  {c.get('method','-')}")

    return 0


# ── main dispatcher ──────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    p = _common_parser()
    subs = p.add_subparsers(dest="cmd")

    sc = subs.add_parser("collect", parents=[_common_parser(add_help=False)])
    sb = subs.add_parser("batch", parents=[_common_parser(add_help=False)])
    sf = subs.add_parser("backfill", parents=[_common_parser(add_help=False)])
    sf.add_argument("--days", default=120, type=int)

    ss = subs.add_parser("status", parents=[_common_parser(add_help=False)])

    sm = subs.add_parser("mappings", parents=[_common_parser(add_help=False)])
    sm.add_argument("--show", action="store_true")
    sm.add_argument("--purge", action="store_true")

    sh = subs.add_parser("history", parents=[_common_parser(add_help=False)])
    sh.add_argument("--history-days", default=30, type=int, dest="history_days")

    args = p.parse_args(argv)
    if not args.cmd:
        p.print_help()
        return 1

    ensure_db()

    dispatch = {
        "collect": cmd_collect,
        "batch": cmd_batch,
        "backfill": cmd_backfill,
        "status": cmd_status,
        "mappings": cmd_mappings,
        "history": cmd_history,
    }

    fn = dispatch.get(args.cmd)
    if fn is None:
        print(f"Unknown command: {args.cmd}", file=sys.stderr)
        return 1

    return fn(args)


if __name__ == "__main__":
    sys.exit(main())
