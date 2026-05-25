"""GET /api/buildings — campus and building list handler."""

from __future__ import annotations

import re
from http.server import BaseHTTPRequestHandler
from pathlib import Path

from electrifyszu.config import DormConfig as Config
from electrifyszu.ranking.cache import cached_ranking_for
from electrifyszu.server.handlers.types import (
    ENV_FILE,
    query_value,
    send_json,
    send_error,
)

import electrifyszu.apartment.buildings as _apt_buildings

ROOT = Path(__file__).resolve().parents[3]
BUILDINGS_FILE = ROOT / "room-power-monitor" / "data" / "buildings.txt"


def handle_buildings(handler: BaseHTTPRequestHandler) -> None:
    config = Config.from_env(str(ENV_FILE))
    data = merge_campuses(default_campuses(config), load_buildings_file())
    _merge_apartment_into_lihu(data)
    send_json(handler, {"ok": True, "data": data})


def handle_apartment_floors(handler: BaseHTTPRequestHandler, query: dict[str, list[str]]) -> None:
    try:
        building_code = query_value(query, "building") or ""
        building = _apt_buildings.get_building(building_code)
        floors = [
            {"code": f"{building.code}{f:02d}", "label": building.floor_label(f)}
            for f in building.floors
        ]
        send_json(handler, {"ok": True, "data": {
            "building_code": building.code, "building_name": building.name, "floors": floors,
        }})
    except LookupError as exc:
        send_error(handler, "BUILDING_NOT_FOUND", str(exc), status=404)
    except Exception as exc:
        send_error(handler, "ERROR", str(exc), status=500)


def handle_apartment_rooms(handler: BaseHTTPRequestHandler, query: dict[str, list[str]]) -> None:
    try:
        building_code = query_value(query, "building") or ""
        floor_code = query_value(query, "floor") or ""
        building = _apt_buildings.get_building(building_code)
        rooms = [
            {"code": rc, "label": rl}
            for rc, rl in building.iter_rooms()
            if rc[:4] == floor_code[:4]
        ]
        send_json(handler, {"ok": True, "data": {
            "building_code": building.code, "building_name": building.name,
            "floor_code": floor_code, "rooms": rooms,
        }})
    except LookupError as exc:
        send_error(handler, "BUILDING_NOT_FOUND", str(exc), status=404)
    except Exception as exc:
        send_error(handler, "ERROR", str(exc), status=500)


def handle_building_ranking(handler: BaseHTTPRequestHandler, query: dict[str, list[str]]) -> None:
    try:
        config = Config.from_env(str(ENV_FILE))
        client = query_value(query, "client") or config.client
        building_id = query_value(query, "buildingId") or config.building_id
        result = cached_ranking_for(load_ranking_cache_from_cache(), client=client, building_id=building_id)
        if result is None:
            send_json(handler, {"ok": False, "error": "未找到该楼栋的本地排行缓存。"}, status=404)
            return
        send_json(handler, {"ok": True, "data": result})
    except Exception as exc:
        send_json(handler, {"ok": False, "error": str(exc)}, status=502)


def load_ranking_cache_from_cache() -> dict:
    from electrifyszu.ranking.cache import load_ranking_cache as lrc
    return lrc()


# ── Buildings utilities ──────────────────────────────────────────────────────

def load_buildings_file() -> list[dict[str, object]]:
    campuses: list[dict[str, object]] = []
    if not BUILDINGS_FILE.is_file():
        return campuses

    campus_pattern = re.compile(r"^##\s+(.+?)\s+client=([^\s]+)")
    building_pattern = re.compile(r"buildingId=\s*(\d+)\s+(.+?)\s*$")
    current: dict[str, object] | None = None
    for line in BUILDINGS_FILE.read_text(encoding="utf-8").splitlines():
        campus_match = campus_pattern.search(line)
        if campus_match:
            current = {
                "client": campus_match.group(2).strip(),
                "name": campus_match.group(1).strip(),
                "buildings": [],
            }
            campuses.append(current)
            continue
        building_match = building_pattern.search(line)
        if building_match and current is not None:
            current["buildings"].append({
                "id": building_match.group(1),
                "name": building_match.group(2).strip(),
            })
    return campuses


def default_campuses(config: Config) -> list[dict[str, object]]:
    return [{
        "client": config.client,
        "name": config.campus_name,
        "buildings": [{"id": config.building_id, "name": config.building_name}],
    }]


def merge_campuses(*groups: list[dict[str, object]]) -> list[dict[str, object]]:
    merged: list[dict[str, object]] = []
    campuses_by_client: dict[str, dict[str, object]] = {}
    for group in groups:
        for campus in group:
            client = str(campus.get("client", "")).strip()
            name = str(campus.get("name", "")).strip()
            if not client:
                continue
            target = campuses_by_client.get(client)
            if target is None:
                target = {"client": client, "name": name, "buildings": []}
                campuses_by_client[client] = target
                merged.append(target)
            seen_buildings = {building["id"] for building in target["buildings"]}
            for building in campus.get("buildings", []):
                building_id = str(building.get("id", "")).strip()
                building_name = str(building.get("name", "")).strip()
                if building_id and building_id not in seen_buildings:
                    target["buildings"].append({"id": building_id, "name": building_name})
                    seen_buildings.add(building_id)
    return merged


def _merge_apartment_into_lihu(data: list[dict[str, object]]) -> None:
    try:
        apartments = _apt_buildings.load_buildings()
        apt_list = [
            {"id": b.code, "name": b.name}
            for b in sorted(apartments.values(), key=lambda x: x.code)
        ]
    except Exception:
        return
    for campus in data:
        if campus.get("client") == "172.21.101.11":
            seen = {b["id"] for b in campus.get("buildings", [])}
            for building in apt_list:
                if building["id"] not in seen:
                    campus["buildings"].append(building)
                    seen.add(building["id"])
            return
    data.append({
        "client": "172.21.101.11",
        "name": "西丽校区",
        "buildings": apt_list,
    })
