"""Unified collection engine — adapts both dorm and apartment APIs.

Each call to collect_one_room() produces a persisted snapshot with
expanded daily-consumption and charge-event children.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from electrifyszu.config import DormConfig, ApartmentConfig
from electrifyszu.dorm.api import DormApi
from electrifyszu.dorm.discover import discover_room_id
import electrifyszu.apartment.api as _apt_mod
from electrifyszu.archive.mapping_repo import MappingRepository
from electrifyszu.archive.snapshot_repo import SnapshotStorage

log = logging.getLogger("electrifyszu.archive.collector")


@dataclass
class CollectResult:
    ok: bool
    latency_ms: int = 0
    snapshot_id: int = 0
    error: str = ""

    @staticmethod
    def success(snapshot_id: int = 0, latency_ms: int = 0) -> "CollectResult":
        return CollectResult(ok=True, snapshot_id=snapshot_id, latency_ms=latency_ms)

    @staticmethod
    def fail(msg: str) -> "CollectResult":
        return CollectResult(ok=False, error=msg)


class PowerCollector:
    """Facade over dorm/apartment APIs with automatic archiving."""

    def __init__(self) -> None:
        self.repo = MappingRepository()
        self.store = SnapshotStorage()

    # ── public entry ────────────────────────────────────────────────

    def collect_one_room(
        self,
        *,
        source: str,
        client: str,
        campus_name: str,
        building_id: str,
        building_name: str,
        room_name: str,
        days: int = 30,
    ) -> CollectResult:
        t0 = time.monotonic()
        try:
            if source == "dorm":
                return self._collect_dorm(client, campus_name, building_id,
                                          building_name, room_name, days, t0)
            if source == "apartment":
                return self._collect_apt(client, campus_name, building_id,
                                        building_name, room_name, days, t0)
            return CollectResult.fail(f"unknown source: {source}")
        except Exception as exc:
            ms = int((time.monotonic() - t0) * 1000)
            log.exception("collect %s %s %s failed", building_name, room_name, exc)
            return CollectResult.fail(str(exc)[:200])

    # ── dorm path ───────────────────────────────────────────────────

    def _collect_dorm(self, client, campus_name, building_id,
                      building_name, room_name, days, t0) -> CollectResult:
        room_id = discover_room_id(building_id, room_name, client_ip=client)
        if not room_id:
            return CollectResult.fail("room_id not found")

        cfg = DormConfig.from_env()
        cfg.client = client
        api = DormApi(cfg)
        status = api.get_status(room_id, room_name, days=days)

        lat = int((time.monotonic() - t0) * 1000)
        sid = self.store.ingest_status(
            source="dorm", client=client,
            campus_name=campus_name,
            building_id=building_id, building_name=building_name,
            room_name=room_name, status=status,
            captured_at=datetime.now().isoformat(),
            latency_ms=lat,
        )
        log.info("collected dorm %s %s %.1fs snap=%d",
                 building_name, room_name, lat/1000, sid)
        return CollectResult.success(sid, lat)

    # ── apartment path ──────────────────────────────────────────────

    def _collect_apt(self, client, campus_name, building_id,
                     building_name, room_name, days, t0) -> CollectResult:
        cfg = ApartmentConfig.from_env()
        api = _apt_mod.ApartmentPowerApi(cfg)
        status = api.get_status(building_id, room_name, days=days)

        # Cache the room_code (=internal_id) for apartment too
        rc = status.get("room_code")
        if rc:
            self.repo.put_internal_id(
                source="apartment", client=client,
                campus_name=campus_name,
                building_id=building_id, building_name=building_name,
                room_name=room_name, internal_id=rc,
            )

        lat = int((time.monotonic() - t0) * 1000)
        sid = self.store.ingest_status(
            source="apartment", client=client,
            campus_name=campus_name,
            building_id=building_id, building_name=building_name,
            room_name=room_name, status=status,
            captured_at=datetime.now().isoformat(),
            latency_ms=lat,
        )
        log.info("collected apt %s %s %.1fs snap=%d",
                 building_name, room_name, lat/1000, sid)
        return CollectResult.success(sid, lat)

    # ── multi-day backfill ──────────────────────────────────────────

    def backfill_room(
        self,
        *,
        source: str,
        client: str,
        campus_name: str,
        building_id: str,
        building_name: str,
        room_name: str,
        days: int = 120,
    ) -> list[CollectResult]:
        """Pull several months of history by iterating monthly chunks.

        The campus systems typically retain 1-5 years of meter readings.
        We ask for larger *days* spans and let the backend paginate.
        """
        from datetime import date, timedelta

        today = date.today()
        begin = today - timedelta(days=days)
        chunk_results: list[CollectResult] = []

        # Resolve mapping upfront so each chunk reuses it
        if source == "dorm":
            discover_room_id(building_id, room_name, client_ip=client,
                            force_rediscover=True)

        # Grab one big-period status (backend supports wide ranges)
        res = self.collect_one_room(
            source=source, client=client,
            campus_name=campus_name,
            building_id=building_id, building_name=building_name,
            room_name=room_name, days=days,
        )
        chunk_results.append(res)
        return chunk_results
