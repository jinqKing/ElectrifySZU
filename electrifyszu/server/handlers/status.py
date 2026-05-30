"""GET /api/status — dormitory power query handler."""

from __future__ import annotations

import logging
from http.server import BaseHTTPRequestHandler

from electrifyszu.config import (
    CAMPUS_GROUP, MAX_QUERY_DAYS,
    DormConfig as Config,
    ApartmentConfig,
    client_for_group,
    group_for_client,
)
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

logger = logging.getLogger("server")

# Ranking cache (lazy-loaded on first request)
_RANKING_CACHE: dict = {}
_RANKING_CACHE_LOADED: bool = False


def _get_ranking_cache() -> dict:
    global _RANKING_CACHE, _RANKING_CACHE_LOADED
    if not _RANKING_CACHE_LOADED:
        _RANKING_CACHE = load_ranking_cache()
        _RANKING_CACHE_LOADED = True
    return _RANKING_CACHE or {}


def handle_status(handler: BaseHTTPRequestHandler, query: dict[str, list[str]]) -> None:
    try:
        client_raw = query_value(query, "client") or ""
        # Accept either campus group name (new) or legacy IP
        client_ip = client_for_group(client_raw) or client_raw
        building_id = query_value(query, "buildingId") or ""
        campus_name = query_value(query, "campusName") or ""
        building_name = query_value(query, "buildingName") or ""
        room_name = query_value(query, "roomName") or ""
        try:
            days = int(query_value(query, "days") or "30")
        except (ValueError, TypeError):
            days = 30
        days = min(max(days, 1), MAX_QUERY_DAYS)

        # 丽湖校区内，公寓系统楼栋（编码01-06）走 ApartmentPowerApi
        lihu_ip = CAMPUS_GROUP.get("lihu", "")
        if (client_raw == "lihu" or client_ip == lihu_ip) and building_id in ("01", "02", "03", "04", "05", "06"):
            _handle_apartment_status(handler, building_id, room_name, days)
            return

        config = Config.from_env(str(ENV_FILE))
        config.client = client_ip or config.client
        room_id = discover_room_id(
            building_id=building_id or config.building_id,
            room_name=room_name or config.room_name,
            client_ip=config.client,
            base_url=config.base_url,
        )
        if not room_id:
            raise LookupError(f"未找到 {campus_name} {building_name} {room_name} 房间。")

        result = DormApi(config).get_status(
            room_id=room_id,
            room_name=room_name or config.room_name,
            days=days,
            threshold=config.low_power_threshold,
        )
        result["client"] = client_raw or group_for_client(config.client)
        result["campus_name"] = campus_name or config.campus_name
        result["building_id"] = building_id or config.building_id
        result["building_name"] = building_name or config.building_name

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
    try:
        apt_config = ApartmentConfig.from_env(str(ENV_FILE))
        api = _apt_api.ApartmentPowerApi(apt_config)
        result = api.get_status(
            building_code=building_code,
            room_name=room_name,
            days=days,
            threshold=apt_config.low_power_threshold,
        )
        result["client"] = "lihu"
        result["campus_name"] = "西丽校区"
        result["building_id"] = building_code
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
