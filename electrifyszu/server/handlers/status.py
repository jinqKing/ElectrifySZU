"""GET /api/status — dormitory power query handler.

Strategy: cache-first. Attempts to serve a fresh snapshot (<24h) from the
power-archive SQLite tables before falling back to a live campus-network
scrape. Live fetches persist their results for subsequent cache hits.
"""

from __future__ import annotations

import logging
from http.server import BaseHTTPRequestHandler

from electrifyszu.config import CAMPUS_GROUP, DormConfig as Config, ApartmentConfig
from electrifyszu.dorm.api import DormApi
from electrifyszu.dorm.discover import discover_room_id
from electrifyszu.ranking.cache import cached_ranking_for, load_ranking_cache
from electrifyszu.server.handlers.types import (
    ENV_FILE,
    query_value,
    send_error,
    send_json,
)

import electrifyszu.apartment.api as _apt_api
from electrifyszu.archive.snapshot_repo import SnapshotStorage

logger = logging.getLogger("server")

# Ranking cache (lazy-loaded on first request)
_RANKING_CACHE: dict = {}
_RANKING_CACHE_LOADED: bool = False

# Singleton snapshot store (thread-safe via thread-local conn)
_SSTORE: SnapshotStorage | None = None


def _snapshot_store() -> SnapshotStorage:
    global _SSTORE
    if _SSTORE is None:
        _SSTORE = SnapshotStorage()
    return _SSTORE


def _get_ranking_cache() -> dict:
    global _RANKING_CACHE, _RANKING_CACHE_LOADED
    if not _RANKING_CACHE_LOADED:
        _RANKING_CACHE = load_ranking_cache()
        _RANKING_CACHE_LOADED = True
    return _RANKING_CACHE or {}


def handle_status(handler: BaseHTTPRequestHandler, query: dict[str, list[str]]) -> None:
    try:
        client = query_value(query, "client") or ""
        building_id = query_value(query, "buildingId") or ""
        campus_name = query_value(query, "campusName") or ""
        building_name = query_value(query, "buildingName") or ""
        room_name = query_value(query, "roomName") or ""
        days = int(query_value(query, "days") or "30")

        # 丽湖校区内，公寓系统楼栋（编码01-06）走 ApartmentPowerApi
        if client == CAMPUS_GROUP["lihu"] and building_id in ("01", "02", "03", "04", "05", "06"):
            _handle_apartment_status(handler, building_id, room_name, days)
            return

        config = Config.from_env(str(ENV_FILE))
        config.client = client or config.client
        eff_client = client or config.client
        eff_bi = building_id or config.building_id
        eff_rn = room_name or config.room_name

        # ── Cache-fast path: try archive snapshot ≤24h ──
        cached_result: dict | None = None
        try:
            snap = _snapshot_store().latest_snapshot(
                source="dorm", client=eff_client,
                building_id=eff_bi, room_name=eff_rn,
                max_age_hours=24,
            )
            if snap:
                cached_result = {
                    "remaining": snap["remaining"],
                    "total_used_kwh": snap["total_used_kwh"],
                    "daily_avg_kwh": snap["daily_avg_kwh"],
                    "est_days_left": snap["est_days_left"],
                    "unit_price": snap["unit_price"],
                    "status": snap["status"],
                    "period": snap["period"],
                    "client": eff_client,
                    "campus_name": campus_name or config.campus_name,
                    "building_id": eff_bi,
                    "building_name": building_name or config.building_name,
                    "_source": "cache",
                    "_captured_at": snap["captured_at"],
                }
                logger.info("cache HIT %s %s (%s)", eff_bi, eff_rn, snap["captured_at"])
        except Exception as cx:
            logger.debug("cache read error (ignoring): %s", cx)

        if cached_result:
            result = cached_result
        else:
            # ── Cache-miss: live fetch ──
            logger.info("cache MISS %s %s — fetching live", eff_bi, eff_rn)
            room_id = discover_room_id(
                building_id=eff_bi,
                room_name=eff_rn,
                client_ip=eff_client,
                base_url=config.base_url,
            )
            if not room_id:
                raise LookupError(f"未找到 {campus_name} {building_name} {eff_rn} 房间。")

            result = DormApi(config).get_status(
                room_id=room_id,
                room_name=eff_rn,
                days=days,
                threshold=config.low_power_threshold,
            )
            result["client"] = eff_client
            result["campus_name"] = campus_name or config.campus_name
            result["building_id"] = eff_bi
            result["building_name"] = building_name or config.building_name
            result["_source"] = "live"

            # Persist fetched result into archive
            try:
                _snapshot_store().ingest_status(
                    source="dorm", client=eff_client,
                    campus_name=result.get("campus_name", ""),
                    building_id=eff_bi, building_name=result.get("building_name", ""),
                    room_name=eff_rn, status=result,
                )
                logger.info("persisted live snapshot %s %s", eff_bi, eff_rn)
            except Exception as px:
                logger.warning("archive ingest error (non-fatal): %s", px)

        # 楼栋排行百分位
        try:
            ranking_data = cached_ranking_for(
                _get_ranking_cache(), client=client, building_id=building_id
            )
            if ranking_data and ranking_data.get("ranking"):
                rows = ranking_data["ranking"]
                user_total = result.get("total_used_kwh")
                if user_total is not None:
                    below = sum(1 for r in rows if r["total_used_kwh"] < user_total)
                    total = len(rows)
                    percentile = round(below / total * 100) if total > 0 else 0
                    result["building_percentile"] = percentile
                    result["building_rank"] = below + 1
                    result["building_rank_total"] = total
        except Exception:
            pass

        send_json(handler, {"ok": True, "data": result})
    except LookupError as exc:
        send_error(
            handler, "ROOM_NOT_FOUND", str(exc),
            "请确认校区、楼栋与房间号是否正确。", status=502,
        )
    except Exception as exc:
        send_error(
            handler, "CAMPUS_NETWORK_ERROR", str(exc),
            "请确认已连接校园网，稍后重试。", status=502,
        )


def _handle_apartment_status(
    handler: BaseHTTPRequestHandler, building_code: str, room_name: str, days: int
) -> None:
    CLIENT_APT = "172.21.101.11"
    CAMPUS_APT = "西丽校区"
    try:
        apt_config = ApartmentConfig.from_env(str(ENV_FILE))

        # ── Cache-fast path ──
        cached_result: dict | None = None
        try:
            snap = _snapshot_store().latest_snapshot(
                source="apartment", client=CLIENT_APT,
                building_id=building_code, room_name=room_name,
                max_age_hours=24,
            )
            if snap:
                cached_result = {
                    "remaining": snap["remaining"],
                    "total_used_kwh": snap["total_used_kwh"],
                    "daily_avg_kwh": snap["daily_avg_kwh"],
                    "est_days_left": snap["est_days_left"],
                    "unit_price": snap["unit_price"],
                    "status": snap["status"],
                    "period": snap["period"],
                    "client": CLIENT_APT,
                    "campus_name": CAMPUS_APT,
                    "building_id": building_code,
                    "_source": "cache",
                    "_captured_at": snap["captured_at"],
                }
                logger.info("apt cache HIT %s %s", building_code, room_name)
        except Exception as cx:
            logger.debug("apt cache read error (ignoring): %s", cx)

        if cached_result:
            result = cached_result
        else:
            # ── Cache-miss: live fetch ──
            logger.info("apt cache MISS %s %s — fetching live", building_code, room_name)
            api = _apt_api.ApartmentPowerApi(apt_config)
            result = api.get_status(
                building_code=building_code,
                room_name=room_name,
                days=days,
                threshold=apt_config.low_power_threshold,
            )
            result["client"] = CLIENT_APT
            result["campus_name"] = CAMPUS_APT
            result["building_id"] = building_code
            result["_source"] = "live"

            # Persist into archive
            try:
                _snapshot_store().ingest_status(
                    source="apartment", client=CLIENT_APT,
                    campus_name=CAMPUS_APT,
                    building_id=building_code,
                    building_name=result.get("building_name", ""),
                    room_name=room_name, status=result,
                )
                logger.info("persisted apt snapshot %s %s", building_code, room_name)
            except Exception as px:
                logger.warning("apt archive ingest error (non-fatal): %s", px)

 (feat: integrate Power Archive into server and alerts workflows)
        send_json(handler, {"ok": True, "data": result})
    except LookupError as exc:
        send_error(
            handler, "ROOM_NOT_FOUND", str(exc),
            "请确认楼栋与房间号是否正确。", status=502,
        )
    except Exception as exc:
        send_error(
            handler, "CAMPUS_NETWORK_ERROR", str(exc),
            "请确认已连接校园网，稍后重试。", status=502,
        )
