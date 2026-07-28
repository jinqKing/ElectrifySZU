"""Sftest campus power query API client.

Target: sftest.hqb.szu.edu.cn (后勤部新宿舍用电系统)
Protocol: JSON-over-HTTP, no authentication beyond an ``openid`` parameter.
"""

from __future__ import annotations

import json
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
from typing import Any

from electrifyszu.config import SftestConfig as Config, MAX_QUERY_DAYS
from electrifyszu.version import __version__
from electrifyszu.sftest.buildings import get_building, SftestBuilding


# ── Public API ──────────────────────────────────────────────────────────────

class SftestApi:
    """Client for the Sftest student dormitory power query endpoint."""

    def __init__(self, config: Config):
        self.base_url = config.base_url.rstrip("/")
        self.openid = config.openid
        self.access_token = config.access_token
        self.unit_price = config.unit_price
        self.timeout = config.timeout

    def list_buildings(self) -> list[dict[str, str]]:
        """Return known buildings (static registry)."""
        from electrifyszu.sftest.buildings import load_buildings
        return [
            {"code": b.code, "name": b.name, "prefix": b.prefix}
            for b in sorted(load_buildings().values(), key=lambda x: x.code)
        ]

    def get_rooms(self, building_code: str) -> list[dict[str, str]]:
        """Fetch room list for a building from the API."""
        building = get_building(building_code)
        url = f"{self.base_url}/gl/getRoomBu.action?guid={building.guid}"
        data = self._post_json(url)
        return [{"rm_id": r["rm_id"], "rm_guid": r["guid"]} for r in data]

    def get_devices(self, rm_guid: str) -> list[dict[str, str]]:
        """Fetch device (meter) list for a room."""
        url = f"{self.base_url}/gzhnew/findFacdata.action?openid={self.openid}&rmGuid={rm_guid}"
        return self._get_json(url)

    def get_daily_usage(
        self, rm_guid: str, device_guid: str, days: int = 30,
    ) -> dict[str, Any]:
        """Fetch daily usage (type=2 = 30 days, type=1 = 7 days)."""
        type_id = 2 if days > 7 else 1
        url = (
            f"{self.base_url}/gzhnew/getdayUse.action"
            f"?openid={self.openid}&rmGuid={rm_guid}"
            f"&type={type_id}&device_guid={device_guid}"
        )
        return self._get_json(url)

    def get_balance(self, rm_guid: str) -> float | None:
        """Fetch balance (余额, 元), auto-binding the room if we are the first binder.

        The sftest system allows multiple students to bind the same room, but
        only the *first* binder (the room's original owner) can see the
        financial balance.  When a room has no prior owner (*isExit* returns
        0), we bind it transparently so that balance becomes available for
        all future queries.  Rooms already owned by another student will
        return None for balance (usage data remains fully available).

        Requires a valid *access_token* (SFTEST_ACCESS_TOKEN env var).
        At most 3 HTTP round-trips per unbound room (isExit + bindInfo +
        qhCustId); subsequent queries hit the DB cache with 0 overhead.
        """
        if not self.access_token:
            return None

        import re
        from http.cookiejar import CookieJar

        # Helper: one balance attempt
        def _try_balance() -> float | None:
            jar = CookieJar()
            opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
            url = (
                f"{self.base_url}/gzhnew/qhCustId.action"
                f"?openid={self.openid}&rmGuid={rm_guid}"
                f"&access_token={self.access_token}&nickname=api"
            )
            try:
                req = urllib.request.Request(url)
                with opener.open(req, timeout=self.timeout) as resp:
                    final = resp.geturl()
                m = re.search(r"sy=([\d.]+)", final)
                if m:
                    return float(m.group(1))
            except Exception:
                pass
            return None

        # Attempt 1: direct balance query
        result = _try_balance()
        if result is not None:
            return result

        # Attempt 2: check if room is free, bind it, then retry
        try:
            check_url = (
                f"{self.base_url}/gzhnew/isExitOpenidAndRm.action"
                f"?openid={self.openid}&rmGuid={rm_guid}"
            )
            req = urllib.request.Request(check_url)
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                status = resp.read().decode().strip()
        except Exception:
            return None

        if status != "0":
            # Room already bound (to us or someone else).  If it's ours we
            # would have gotten balance in attempt 1, so it's someone else's.
            return None

        # Bind the room
        try:
            bind_url = (
                f"{self.base_url}/gzhnew/bindInfo.action"
                f"?rmGuid={rm_guid}&openid={self.openid}&type=1&nickname=api"
            )
            req = urllib.request.Request(bind_url)
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                pass
        except Exception:
            return None

        # Attempt 3: retry balance after binding
        return _try_balance()

    # ── Main entry point ─────────────────────────────────────────────────

    def get_status(
        self,
        building_code: str,
        room_name: str,
        days: int = 30,
        threshold: float | None = None,
    ) -> dict[str, Any]:
        """Return a dorm-compatible room power summary."""
        from electrifyszu.store import (
            get_usage_gap,
            get_usage_records,
            get_recharge_records,
            insert_usage_records,
            recharge_is_stale,
        )
        from electrifyszu.sftest.store import reconstruct_sftest_status
        from electrifyszu.config import CAMPUS_GROUP

        days = min(max(days, 1), MAX_QUERY_DAYS)
        today = datetime.now()
        begin = (today - timedelta(days=days + 1)).strftime("%Y-%m-%d")
        end = today.strftime("%Y-%m-%d")

        building = get_building(building_code)
        client = CAMPUS_GROUP.get("yuehai_sftest", "sftest")

        # Resolve room: "101" → "DFX-101" → rm_guid
        room_label = f"{building.prefix}-{room_name}"
        rooms = self.get_rooms(building_code)
        rm_guid = None
        for r in rooms:
            if r["rm_id"] == room_label:
                rm_guid = r["rm_guid"]
                break
        if rm_guid is None:
            sample = ", ".join(r["rm_id"] for r in rooms[:5])
            raise LookupError(
                f"未找到 {room_label}；{building.name} 示例房间：{sample}"
            )

        # Get first electric meter
        devices = self.get_devices(rm_guid)
        electric = [d for d in devices if d.get("tj_type") == "0"]
        if not electric:
            raise LookupError(f"{room_label} 没有电表设备")
        device_guid = electric[0]["DEVICE_GUID"]

        # 1. Usage: fill gap, then reconstruct
        gap_begin, gap_end = get_usage_gap(client, rm_guid, begin, end)
        if gap_begin:
            usage = self.get_daily_usage(rm_guid, device_guid, days=days)
            bmdata = usage.get("bmdata", [])
            ydata = usage.get("ydata", [])
            xdata = usage.get("xdata", [])
            if ydata and bmdata and xdata:
                records = []
                for i in range(len(xdata)):
                    kwh = _to_float(ydata[i])
                    if kwh == 0 and i > 0:
                        continue  # skip zero-day filler entries
                    records.append({
                        "record_time": _normalize_date(xdata[i]),
                        "remaining": None,
                        "total_used": _to_float(bmdata[i]) if i < len(bmdata) else None,
                        "daily_kwh": kwh,
                        "unit_price": self.unit_price,
                    })
                if records:
                    insert_usage_records(client, rm_guid, records)

        # Always fetch balance (yuan) — independent of usage gap
        fresh_balance = self.get_balance(rm_guid)

        stored = get_usage_records(client, rm_guid, begin, end)

        # 2. Recharge (sftest has its own recharge API but DB is shared)
        if recharge_is_stale(client, rm_guid):
            try:
                # The findMyCzdata endpoint requires beginTime/endTime;
                # without them it returns [].  Use a wide range to fetch all history.
                cz = self._fetch_recharges(rm_guid, begin_time="2020-01-01", end_time=end)
                if cz:
                    from electrifyszu.store import insert_recharge_records
                    insert_recharge_records(client, rm_guid, [
                        {"recharge_time": r["time"], "kwh": r.get("kwh"),
                         "yuan": r.get("yuan"), "method": r.get("method", "")}
                        for r in cz
                    ])
            except Exception:
                pass
        recharge_stored = get_recharge_records(client, rm_guid)

        # 3. Reconstruct via glue layer
        result = reconstruct_sftest_status(
            stored, recharge_stored,
            rm_guid, room_name, begin, end, days, threshold,
            balance_yuan=fresh_balance,
        )
        result.update({
            "building_code": building.code,
            "building_name": building.name,
            "room_label": room_label,
        })
        return result

    # ── Internal helpers ──────────────────────────────────────────────────

    def _get_json(self, url: str) -> Any:
        req = urllib.request.Request(url, headers={
            "User-Agent": f"ElectrifySZU-Sftest/{__version__}",
        })
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read())

    def _post_json(self, url: str, body: bytes = b"") -> Any:
        req = urllib.request.Request(url, data=body, headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": f"ElectrifySZU-Sftest/{__version__}",
        })
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read())

    def _fetch_recharges(self, rm_guid: str, begin_time: str = "", end_time: str = "") -> list[dict[str, Any]]:
        """Fetch recharge records from the sftest API.

        The endpoint supports optional *beginTime* / *endTime* filters
        (``YYYY-MM-DD``) and requires *access_token* in the query string.

        Response fields: *type* (1-5), *pt_name*, *money* (元), *time*.
        No kWh field is returned; kWh is derived from yuan via unit price.
        """
        if not self.access_token:
            return []
        params = (
            f"openid={self.openid}&access_token={self.access_token}"
            f"&rmGuid={rm_guid}"
        )
        if begin_time:
            params += f"&beginTime={begin_time}"
        if end_time:
            params += f"&endTime={end_time}"
        url = f"{self.base_url}/gzhnew/findMyCzdata.action?{params}"
        raw = self._get_json(url)
        if not isinstance(raw, list):
            return []
        records = []
        TYPE_NAMES = {
            "1": "人工充值",
            "2": "微信支付",
            "3": "支付宝支付",
            "4": "第三方接口充值",
            "5": "结算调整",
        }
        for r in raw:
            time_val = str(r.get("time", ""))
            yuan = _to_float(r.get("money"), default=None)
            # No kWh field from this endpoint; derive from yuan
            kwh = round(yuan / self.unit_price, 6) if yuan is not None and self.unit_price > 0 else None
            type_code = str(r.get("type", ""))
            method = TYPE_NAMES.get(type_code, r.get("pt_name", type_code) or "")
            if time_val:
                records.append({
                    "time": time_val,
                    "kwh": kwh,
                    "yuan": yuan,
                    "method": method,
                })
        return records


# ── Module-level helpers ────────────────────────────────────────────────────

def _to_float(value: Any, default: float | None = 0.0) -> float | None:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return default


def _normalize_date(raw: str) -> str:
    """Convert 'MM-DD' or partial date to ISO-style."""
    raw = str(raw).strip()
    if raw in ("0", ""):
        return ""
    today = datetime.now()
    year = today.year
    # Handle "MM-DD" format
    parts = raw.split("-")
    if len(parts) == 2:
        try:
            month, day = int(parts[0]), int(parts[1])
            if 1 <= month <= 12 and 1 <= day <= 31:
                return f"{year}-{month:02d}-{day:02d}"
        except ValueError:
            pass
    return raw
