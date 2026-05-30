import os
import tempfile
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from typing import Any, Callable

from electrifyszu.config import DormConfig as Config, MAX_QUERY_DAYS
from electrifyszu.version import __version__


class ParsedColumnError(ValueError):
    """Raised when a required Excel column cannot be resolved."""


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
        req = urllib.request.Request(url, headers={"User-Agent": f"ElectrifySZU/{__version__}"})
        from electrifyszu.dorm.proxy import get_safe_proxy
        proxy = get_safe_proxy()
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
        """Return a dashboard-friendly room power summary.

        Incrementally fetches missing date ranges from the campus API and
        stores records permanently in SQLite. Once a day's meter reading is
        stored it is never re-fetched.
        """
        from electrifyszu.dorm.store import (
            get_usage_gap,
            get_usage_records,
            get_recharge_records,
            insert_usage_records,
            insert_recharge_records,
            recharge_is_stale,
            reconstruct_dorm_status,
        )

        days = min(max(days, 1), MAX_QUERY_DAYS)
        today = datetime.now()
        begin = (today - timedelta(days=days + 1)).strftime("%Y-%m-%d")
        end = today.strftime("%Y-%m-%d")

        # 1. Incrementally fill usage gap
        gap_begin, gap_end = get_usage_gap(self.client, room_id, begin, end)
        if gap_begin:
            usage_rows = parse_excel(
                self.get_usage(room_id, room_name, begin=gap_begin, end=gap_end)
            )
            if usage_rows:
                cols = _resolve_usage_columns(usage_rows[0])
                records = [
                    {
                        "record_time": str(r.get(cols["record_time"], "")),
                        "remaining": _to_float(r.get(cols["remaining"])),
                        "total_used": _to_float(r.get(cols["total_used"])),
                    }
                    for r in usage_rows
                ]
                insert_usage_records(self.client, room_id, records)

        # 2. Incrementally fill recharge gap
        if recharge_is_stale(self.client, room_id):
            recharge_rows = parse_excel(self.get_recharge(room_id, room_name))
            if recharge_rows:
                cols = _resolve_recharge_columns(recharge_rows[0])
                records = [
                    {
                        "recharge_time": str(r.get(cols["time"], "")),
                        "kwh": _to_float(r.get(cols["kwh"])),
                        "yuan": _to_float(r.get(cols["yuan"])),
                        "method": str(r.get(cols["method"], "")),
                    }
                    for r in recharge_rows
                ]
                insert_recharge_records(self.client, room_id, records)

        # 3. Reconstruct from DB
        return reconstruct_dorm_status(
            get_usage_records(self.client, room_id, begin, end),
            get_recharge_records(self.client, room_id),
            room_id, room_name, begin, end, days, threshold,
        )


def parse_excel(data: bytes) -> list[dict[str, Any]]:
    """Parse an Excel response into row dictionaries."""
    import xlrd

    tmp = tempfile.NamedTemporaryFile(suffix=".xls", delete=False)
    try:
        tmp.write(data)
        tmp.close()
        workbook = xlrd.open_workbook(tmp.name)
        sheet = workbook.sheets()[0]
        headers = [_clean_header(sheet.cell_value(0, col)) for col in range(sheet.ncols)]
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


def _build_trend(
    records: list[dict[str, Any]],
    usage_columns: dict[str, str],
) -> list[dict[str, Any]]:
    trend: list[dict[str, Any]] = []
    previous_total: float | None = None
    for row in records:
        total = _to_float(row.get(usage_columns["total_used"]))
        daily_used = 0.0 if previous_total is None else max(total - previous_total, 0.0)
        trend.append(
            {
                "date": str(row.get(usage_columns["record_time"], "")),
                "remaining": _to_float(row.get(usage_columns["remaining"])),
                "daily_used_kwh": round(daily_used, 2),
                "total_used_kwh": total,
            }
        )
        previous_total = total
    return trend[1:]


def _clean_header(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _normalize_header(value: Any) -> str:
    text = _clean_header(value)
    ignored_chars = "()\uFF08\uFF09[]\u3010\u3011_-:/"
    return "".join(
        ch.lower() for ch in text if not ch.isspace() and ch not in ignored_chars
    )


def _resolve_usage_columns(row: dict[str, Any]) -> dict[str, str]:
    return _resolve_required_columns(
        row,
        {
            "remaining": [
                _contains("\u5269\u4f59"),
                "\u5269\u4f59\u7535\u91cf",
                "\u5269\u4f59\u7535\u8d39",
                "\u5f53\u524d\u5269\u4f59\u7535\u91cf",
            ],
            "total_used": [
                lambda header: _contains("\u7528\u7535")(header)
                and (
                    _contains("\u603b")(header)
                    or _contains("\u7d2f\u8ba1")(header)
                ),
                "\u603b\u7528\u7535\u91cf",
                "\u7d2f\u8ba1\u7528\u7535\u91cf",
                "\u7d2f\u8ba1\u7528\u7535",
            ],
            "record_time": [
                lambda header: _contains("\u65f6\u95f4")(header)
                or _contains("\u65e5\u671f")(header),
                "\u6284\u8868\u65f6\u95f4",
                "\u8bb0\u5f55\u65f6\u95f4",
                "\u65e5\u671f",
            ],
        },
        dataset_name="usage",
    )


def _resolve_recharge_columns(row: dict[str, Any]) -> dict[str, str]:
    return _resolve_required_columns(
        row,
        {
            "method": [
                lambda header: _contains("\u65b9\u5f0f")(header)
                or _contains("\u6e20\u9053")(header)
                or _contains("\u5f62\u5f0f")(header),
                "\u5145\u503c\u65b9\u5f0f",
                "\u652f\u4ed8\u65b9\u5f0f",
                "\u8d2d\u4e70\u5f62\u5f0f",
            ],
            "kwh": [
                lambda header: (
                    _contains("\u5145\u503c")(header)
                    or _contains("\u8d2d\u4e70")(header)
                )
                and (
                    _contains("\u7535")(header)
                    or _contains("\u91cf")(header)
                    or _contains("\u5ea6")(header)
                ),
                "\u5145\u503c\u7535\u91cf",
                "\u5145\u503c\u6570\u91cf",
                "\u5145\u503c\u5ea6\u6570",
                "\u8d2d\u4e70\u7535\u91cf",
                "\u8d2d\u4e70\u7535\u91cf\u5ea6",
            ],
            "yuan": [
                lambda header: _contains("\u91d1\u989d")(header)
                or (
                    _contains("\u5145\u503c")(header)
                    or _contains("\u8d2d\u4e70")(header)
                )
                and _contains("\u5143")(header),
                "\u5145\u503c\u91d1\u989d",
                "\u652f\u4ed8\u91d1\u989d",
                "\u91d1\u989d",
            ],
            "time": [
                lambda header: _contains("\u65f6\u95f4")(header)
                or _contains("\u65e5\u671f")(header),
                "\u5145\u503c\u65f6\u95f4",
                "\u4ea4\u6613\u65f6\u95f4",
                "\u8d2d\u4e70\u65e5\u671f",
                "\u65e5\u671f",
            ],
        },
        dataset_name="recharge",
    )


def _contains(text: str) -> Callable[[str], bool]:
    normalized = _normalize_header(text)
    return lambda header: normalized in header


def _resolve_required_columns(
    row: dict[str, Any],
    required_columns: dict[str, list[Callable[[str], bool] | str]],
    dataset_name: str,
) -> dict[str, str]:
    headers = list(row.keys())
    normalized_headers = {_normalize_header(header): header for header in headers}
    resolved: dict[str, str] = {}
    missing: list[str] = []

    for field_name, matchers in required_columns.items():
        resolved_header = _match_header(headers, normalized_headers, matchers)
        if resolved_header is None:
            missing.append(field_name)
            continue
        resolved[field_name] = resolved_header

    if missing:
        available = ", ".join(_clean_header(header) or "<empty>" for header in headers) or "<none>"
        raise ParsedColumnError(
            f"Missing required {dataset_name} column(s): {', '.join(missing)}. "
            f"Available headers: {available}"
        )

    return resolved


def _match_header(
    headers: list[str],
    normalized_headers: dict[str, str],
    matchers: list[Callable[[str], bool] | str],
) -> str | None:
    for matcher in matchers:
        if callable(matcher):
            for header in headers:
                if matcher(_normalize_header(header)):
                    return header
            continue

        matched = normalized_headers.get(_normalize_header(matcher))
        if matched is not None:
            return matched

    return None
