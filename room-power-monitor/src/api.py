import os
import tempfile
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from typing import Any

from .config import Config


class DormApi:
    """Client for the SZU dormitory power query endpoint."""

    def __init__(self, config: Config):
        self.base_url = config.base_url.rstrip("/")
        self.client = config.client
        self.timeout = 10

    def _build_url(
        self,
        type_id: int,
        room_id: str,
        room_name: str,
        begin: str,
        end: str,
    ) -> str:
        params = urllib.parse.urlencode(
            {
                "type": type_id,
                "beginTime": begin,
                "endTime": end,
                "client": self.client,
                "roomId": room_id,
                "roomName": room_name,
            }
        )
        return f"{self.base_url}/selectList.do?{params}"

    def _fetch(self, url: str) -> bytes:
        req = urllib.request.Request(url, headers={"User-Agent": "ElectrifySZU/0.1"})
        proxy = os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy")
        if proxy:
            handler = urllib.request.ProxyHandler({"http": proxy, "https": proxy})
            opener = urllib.request.build_opener(handler)
            resp = opener.open(req, timeout=self.timeout)
        else:
            resp = urllib.request.urlopen(req, timeout=self.timeout)
        return resp.read()

    def get_recharge(
        self,
        room_id: str,
        room_name: str,
        begin: str = "",
        end: str = "",
    ) -> bytes:
        """Fetch recharge records as Excel bytes."""
        if not begin:
            begin = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        if not end:
            end = datetime.now().strftime("%Y-%m-%d")
        return self._fetch(self._build_url(3, room_id, room_name, begin, end))

    def get_usage(
        self,
        room_id: str,
        room_name: str,
        begin: str = "",
        end: str = "",
        as_excel: bool = True,
    ) -> bytes:
        """Fetch usage records as Excel or HTML bytes."""
        if not begin:
            begin = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        if not end:
            end = datetime.now().strftime("%Y-%m-%d")
        type_id = 5 if as_excel else 7
        return self._fetch(self._build_url(type_id, room_id, room_name, begin, end))

    def get_status(
        self,
        room_id: str,
        room_name: str,
        days: int = 30,
        threshold: float | None = None,
    ) -> dict[str, Any]:
        """Return a dashboard-friendly room power summary."""
        days = max(days, 1)
        today = datetime.now()
        begin = (today - timedelta(days=days)).strftime("%Y-%m-%d")
        end = today.strftime("%Y-%m-%d")

        usage = parse_excel(self.get_usage(room_id, room_name, begin=begin, end=end))
        recharge = parse_excel(self.get_recharge(room_id, room_name))

        result: dict[str, Any] = {
            "room_id": room_id,
            "room_name": room_name,
            "period": {"begin": begin, "end": end, "days": days},
            "records": len(usage),
            "threshold_kwh": threshold,
            "status": "unknown",
            "recharges": [],
            "trend": [],
        }

        if usage:
            first = usage[0]
            last = usage[-1]
            keys = list(first.keys())
            remaining = _to_float(last.get(keys[2]))
            total_used = max(_to_float(last.get(keys[3])) - _to_float(first.get(keys[3])), 0)
            daily_avg = round(total_used / max(len(usage), 1), 2)
            result["trend"] = _build_trend(usage, keys)

            result.update(
                {
                    "remaining": remaining,
                    "total_used_kwh": round(total_used, 2),
                    "daily_avg_kwh": daily_avg,
                    "est_days_left": round(remaining / daily_avg, 1)
                    if daily_avg > 0
                    else None,
                    "last_record": last.get(keys[5]),
                    "status": _status_level(remaining, threshold),
                }
            )

        if recharge:
            result["recharges"] = [
                {
                    "time": row.get(list(row.keys())[6]),
                    "kwh": _to_float(row.get(list(row.keys())[4])),
                    "yuan": _to_float(row.get(list(row.keys())[5])),
                    "method": row.get(list(row.keys())[3]),
                }
                for row in recharge
            ]

        return result


def parse_excel(data: bytes) -> list[dict[str, Any]]:
    """Parse an Excel response into row dictionaries."""
    import xlrd

    tmp = tempfile.NamedTemporaryFile(suffix=".xls", delete=False)
    try:
        tmp.write(data)
        tmp.close()
        workbook = xlrd.open_workbook(tmp.name)
        sheet = workbook.sheets()[0]
        headers = [sheet.cell_value(0, col) for col in range(sheet.ncols)]
        return [
            {headers[col]: sheet.cell_value(row, col) for col in range(sheet.ncols)}
            for row in range(1, sheet.nrows)
        ]
    finally:
        tmp.close()
        os.unlink(tmp.name)


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _status_level(remaining: float, threshold: float | None) -> str:
    if remaining <= 10:
        return "critical"
    if threshold is not None and remaining <= threshold:
        return "low"
    return "ok"


def _build_trend(records: list[dict[str, Any]], keys: list[Any]) -> list[dict[str, Any]]:
    trend: list[dict[str, Any]] = []
    previous_total: float | None = None
    for row in records:
        total = _to_float(row.get(keys[3]))
        daily_used = 0.0 if previous_total is None else max(total - previous_total, 0.0)
        trend.append(
            {
                "date": str(row.get(keys[5], "")),
                "remaining": _to_float(row.get(keys[2])),
                "daily_used_kwh": round(daily_used, 2),
                "total_used_kwh": total,
            }
        )
        previous_total = total
    return trend
