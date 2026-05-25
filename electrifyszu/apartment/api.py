from __future__ import annotations

import html
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta
from html.parser import HTMLParser
from http.cookiejar import CookieJar
from typing import Any

from electrifyszu.apartment.buildings import Building, get_building, load_buildings, normalize_building_code
from electrifyszu.config import ApartmentConfig as Config
from electrifyszu.version import __version__

SELECT_FIELDS = {
    "drlouming": "",
    "drceng": "",
    "drfangjian": "",
    "radio": "",
}


@dataclass
class SelectOption:
    value: str
    label: str


@dataclass
class QueryResult:
    building_code: str
    building_name: str
    floor_code: str
    room_code: str
    room_name: str
    room_label: str
    remaining: float | None
    begin: str
    end: str
    record_type: str
    records: list[dict[str, Any]]


@dataclass
class _FormPage:
    url: str
    html: str
    hidden: dict[str, str]
    selects: dict[str, list[SelectOption]]
    forms: list[dict[str, str]]
    tables: list[list[list[str]]]


class ApartmentPowerApi:
    """Client for http://172.25.100.105:8010/ WebForms power records."""

    def __init__(self, config: Config):
        self.base_url = _normalize_base_url(config.base_url)
        self.timeout = config.timeout

    def list_buildings(self, online: bool = False) -> list[SelectOption]:
        if not online:
            return [
                SelectOption(value=building.code, label=building.name)
                for building in load_buildings().values()
            ]
        opener = self._new_opener()
        page = self._get(opener, self.base_url)
        return _non_empty_options(page.selects.get("drlouming", []))

    def list_floors(self, building_code: str) -> list[SelectOption]:
        opener = self._new_opener()
        home = self._get(opener, self.base_url)
        page = self._select_building(opener, home, building_code)
        return _non_empty_options(page.selects.get("drceng", []))

    def list_rooms(self, building_code: str, floor_code: str) -> list[SelectOption]:
        opener = self._new_opener()
        home = self._get(opener, self.base_url)
        building_page = self._select_building(opener, home, building_code)
        floor_page = self._select_floor(opener, building_page, building_code, floor_code)
        return _non_empty_options(floor_page.selects.get("drfangjian", []))

    def query_usage(
        self,
        building_code: str,
        room_name: str,
        begin: str = "",
        end: str = "",
        max_pages: int | None = None,
    ) -> QueryResult:
        if not begin:
            begin = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        if not end:
            end = datetime.now().strftime("%Y-%m-%d")
        return self._query_records(
            building_code=building_code,
            room_name=room_name,
            record_type="usage",
            begin=begin,
            end=end,
            max_pages=max_pages,
        )

    def query_recharge(
        self,
        building_code: str,
        room_name: str,
        begin: str = "",
        end: str = "",
        max_pages: int | None = None,
    ) -> QueryResult:
        if not begin:
            begin = (datetime.now() - timedelta(days=180)).strftime("%Y-%m-%d")
        if not end:
            end = datetime.now().strftime("%Y-%m-%d")
        return self._query_records(
            building_code=building_code,
            room_name=room_name,
            record_type="recharge",
            begin=begin,
            end=end,
            max_pages=max_pages,
        )

    def get_status(
        self,
        building_code: str,
        room_name: str,
        days: int = 30,
        threshold: float | None = None,
    ) -> dict[str, Any]:
        days = max(days, 1)
        today = datetime.now()
        begin = (today - timedelta(days=days)).strftime("%Y-%m-%d")
        end = today.strftime("%Y-%m-%d")

        usage = self.query_usage(building_code, room_name, begin=begin, end=end)
        recharge = self.query_recharge(building_code, room_name)
        usage_records = _normalize_usage_records(usage.records)
        recharge_records = _normalize_recharge_records(recharge.records)

        total_used = round(sum(row["kwh"] for row in usage_records), 2)
        daily_avg = round(total_used / max(len(usage_records), 1), 2)
        remaining = usage.remaining

        return {
            "building_code": usage.building_code,
            "building_name": usage.building_name,
            "floor_code": usage.floor_code,
            "room_code": usage.room_code,
            "room_name": room_name,
            "room_label": usage.room_label,
            "period": {"begin": begin, "end": end, "days": days},
            "records": len(usage_records),
            "threshold_kwh": threshold,
            "status": _status_level(remaining, threshold),
            "remaining": remaining,
            "total_used_kwh": total_used,
            "daily_avg_kwh": daily_avg,
            "est_days_left": round(remaining / daily_avg, 1)
            if remaining is not None and daily_avg > 0
            else None,
            "last_record": max((row["date"] for row in usage_records), default=""),
            "unit_price": _last_unit_price(usage_records),
            "trend": _build_trend(usage_records, remaining),
            "recharges": recharge_records,
        }

    def _query_records(
        self,
        building_code: str,
        room_name: str,
        record_type: str,
        begin: str,
        end: str,
        max_pages: int | None,
    ) -> QueryResult:
        building = get_building(building_code)
        room_code = building.room_code(room_name)
        floor_code = building.floor_code(room_name)
        room_label = building.room_label(room_name)

        opener = self._new_opener()
        home = self._get(opener, self.base_url)
        building_page = self._select_building(opener, home, building.code)
        floor_page = self._select_floor(opener, building_page, building.code, floor_code)
        self._assert_room_exists(floor_page, room_code, room_label)

        landing = self._enter_record_page(
            opener=opener,
            page=floor_page,
            building=building,
            floor_code=floor_code,
            room_code=room_code,
            record_type=record_type,
        )
        action_url = urllib.parse.urljoin(self.base_url, _form_action(landing, record_type))
        page = self._post(
            opener,
            action_url,
            {
                **landing.hidden,
                "txtstart": begin,
                "txtend": end,
                "btnser": "查询",
            },
            referer=landing.url,
        )

        records = _records_from_page(page, record_type)
        total_pages = _total_pages(page.html)
        if max_pages is not None:
            total_pages = min(total_pages, max_pages)
        for page_no in range(2, total_pages + 1):
            paged = self._get(opener, f"{action_url}?p={page_no}", referer=action_url)
            records.extend(_records_from_page(paged, record_type))

        records = _filter_records_by_date(records, begin, end)

        return QueryResult(
            building_code=building.code,
            building_name=building.name,
            floor_code=floor_code,
            room_code=room_code,
            room_name=room_name,
            room_label=room_label,
            remaining=_parse_remaining(landing.html) or _parse_remaining(page.html),
            begin=begin,
            end=end,
            record_type=record_type,
            records=records,
        )

    def _select_building(
        self,
        opener: urllib.request.OpenerDirector,
        page: _FormPage,
        building_code: str,
    ) -> _FormPage:
        code = normalize_building_code(building_code)
        return self._post(
            opener,
            self.base_url,
            _home_payload(
                page,
                __EVENTTARGET="drlouming",
                __EVENTARGUMENT="",
                drlouming=code,
            ),
            referer=page.url,
        )

    def _select_floor(
        self,
        opener: urllib.request.OpenerDirector,
        page: _FormPage,
        building_code: str,
        floor_code: str,
    ) -> _FormPage:
        return self._post(
            opener,
            self.base_url,
            _home_payload(
                page,
                __EVENTTARGET="drceng",
                __EVENTARGUMENT="",
                drlouming=normalize_building_code(building_code),
                drceng=floor_code,
            ),
            referer=page.url,
        )

    def _enter_record_page(
        self,
        opener: urllib.request.OpenerDirector,
        page: _FormPage,
        building: Building,
        floor_code: str,
        room_code: str,
        record_type: str,
    ) -> _FormPage:
        radio = {"usage": "usedR", "recharge": "buyR"}[record_type]
        return self._post(
            opener,
            self.base_url,
            _home_payload(
                page,
                drlouming=building.code,
                drceng=floor_code,
                drfangjian=room_code,
                radio=radio,
                **{"ImageButton1.x": "20", "ImageButton1.y": "10"},
            ),
            referer=page.url,
        )

    def _assert_room_exists(self, page: _FormPage, room_code: str, room_label: str) -> None:
        options = _non_empty_options(page.selects.get("drfangjian", []))
        if any(option.value == room_code for option in options):
            return
        sample = ", ".join(option.label for option in options[:5]) or "空"
        raise LookupError(f"页面未找到 {room_label}({room_code})；当前楼层房间示例：{sample}")

    def _new_opener(self) -> urllib.request.OpenerDirector:
        return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))

    def _get(
        self,
        opener: urllib.request.OpenerDirector,
        url: str,
        referer: str = "",
    ) -> _FormPage:
        return self._request(opener, url, data=None, referer=referer)

    def _post(
        self,
        opener: urllib.request.OpenerDirector,
        url: str,
        data: dict[str, str],
        referer: str = "",
    ) -> _FormPage:
        return self._request(opener, url, data=data, referer=referer)

    def _request(
        self,
        opener: urllib.request.OpenerDirector,
        url: str,
        data: dict[str, str] | None,
        referer: str = "",
    ) -> _FormPage:
        headers = {"User-Agent": f"ElectrifySZU-Apartment/{__version__}"}
        if referer:
            headers["Referer"] = referer
        body = None
        if data is not None:
            headers["Content-Type"] = "application/x-www-form-urlencoded"
            body = urllib.parse.urlencode(data).encode("ascii")

        req = urllib.request.Request(url, data=body, headers=headers)
        resp = opener.open(req, timeout=self.timeout)
        raw = resp.read()
        charset = _response_charset(resp.headers.get("Content-Type", ""))
        page_html = raw.decode(charset, errors="replace")
        parser = _PageParser()
        parser.feed(page_html)
        return _FormPage(
            url=resp.geturl(),
            html=page_html,
            hidden=parser.hidden,
            selects=parser.selects,
            forms=parser.forms,
            tables=parser.tables,
        )


class _PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hidden: dict[str, str] = {}
        self.selects: dict[str, list[SelectOption]] = {}
        self.forms: list[dict[str, str]] = []
        self.tables: list[list[list[str]]] = []
        self._select_name: str | None = None
        self._option_value: str | None = None
        self._option_text: list[str] = []
        self._table: list[list[str]] | None = None
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        data = {key: value or "" for key, value in attrs}
        if tag == "form":
            self.forms.append(data)
        elif tag == "input":
            if data.get("type") == "hidden" and data.get("name"):
                self.hidden[data["name"]] = data.get("value", "")
        elif tag == "select":
            self._select_name = data.get("name", "")
            self.selects.setdefault(self._select_name, [])
        elif tag == "option" and self._select_name is not None:
            self._option_value = data.get("value", "")
            self._option_text = []
        elif tag == "table":
            self._table = []
        elif tag == "tr" and self._table is not None:
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._cell = []

    def handle_data(self, data: str) -> None:
        if self._option_value is not None:
            self._option_text.append(data)
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "option" and self._select_name is not None and self._option_value is not None:
            self.selects[self._select_name].append(
                SelectOption(
                    value=self._option_value,
                    label=_clean_text("".join(self._option_text)),
                )
            )
            self._option_value = None
            self._option_text = []
        elif tag == "select":
            self._select_name = None
        elif tag in {"td", "th"} and self._cell is not None and self._row is not None:
            self._row.append(_clean_text("".join(self._cell)))
            self._cell = None
        elif tag == "tr" and self._row is not None and self._table is not None:
            if self._row:
                self._table.append(self._row)
            self._row = None
        elif tag == "table" and self._table is not None:
            self.tables.append(self._table)
            self._table = None


def _home_payload(page: _FormPage, **overrides: str) -> dict[str, str]:
    payload = {**page.hidden, **SELECT_FIELDS}
    payload.update(overrides)
    return payload


def _non_empty_options(options: list[SelectOption]) -> list[SelectOption]:
    return [option for option in options if option.value]


def _records_from_page(page: _FormPage, record_type: str) -> list[dict[str, Any]]:
    if not page.tables:
        return []
    table = max(page.tables, key=len)
    if len(table) < 2:
        return []
    headers = table[0]
    records = []
    for row in table[1:]:
        if len(row) != len(headers):
            continue
        item = {headers[index]: row[index] for index in range(len(headers))}
        if _looks_like_record(item, record_type):
            records.append(item)
    return records


def _looks_like_record(item: dict[str, Any], record_type: str) -> bool:
    first = str(next(iter(item.values()), ""))
    if not re.search(r"\d{4}[-/]\d{1,2}[-/]\d{1,2}", first):
        return False
    return "用量(度)" in item if record_type == "usage" else "充值电量(度)" in item


def _form_action(page: _FormPage, record_type: str) -> str:
    default = "./usedRecord.aspx" if record_type == "usage" else "./buyRecord.aspx"
    if not page.forms:
        return default
    return page.forms[0].get("action") or default


def _parse_remaining(page_html: str) -> float | None:
    match = re.search(
        r"剩余电量[：:]\s*<span[^>]*>\s*([^<]+?)\s*</span>",
        page_html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return None
    return _to_float(html.unescape(match.group(1)).strip(), default=None)


def _total_pages(page_html: str) -> int:
    match = re.search(r"第\s*\d+\s*页\s*/\s*共\s*(\d+)\s*页", page_html)
    if not match:
        return 1
    return max(int(match.group(1)), 1)


def _normalize_usage_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = [
        {
            "date": str(row.get("日期", "")).strip(),
            "room": str(row.get("房间名称", "")).strip(),
            "kwh": _to_float(row.get("用量(度)")),
            "unit_price": _to_float(row.get("单价(元/度)")),
        }
        for row in records
    ]
    return sorted(rows, key=lambda item: _date_sort_key(item["date"]))


def _normalize_recharge_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = [
        {
            "time": str(row.get("日期", "")).strip(),
            "room": str(row.get("房间名称", "")).strip(),
            "kwh": _to_float(row.get("充值电量(度)")),
            "yuan": _to_float(row.get("充值金额(元)")),
            "person": str(row.get("充值人", "")).strip(),
        }
        for row in records
    ]
    return sorted(rows, key=lambda item: _date_sort_key(item["time"]), reverse=True)


def _filter_records_by_date(
    records: list[dict[str, Any]],
    begin: str,
    end: str,
) -> list[dict[str, Any]]:
    begin_date = _date_sort_key(begin)
    end_date = _date_sort_key(end)
    if begin_date == datetime.min or end_date == datetime.min:
        return records

    filtered = []
    for record in records:
        record_date = _date_sort_key(str(record.get("日期", "")))
        if record_date == datetime.min:
            continue
        record_day = record_date.replace(hour=0, minute=0, second=0, microsecond=0)
        if begin_date <= record_day <= end_date:
            filtered.append(record)
    return filtered


def _build_trend(
    usage_records: list[dict[str, Any]],
    remaining: float | None,
) -> list[dict[str, Any]]:
    trend: list[dict[str, Any]] = []
    if remaining is None:
        for row in usage_records:
            trend.append({"date": row["date"], "daily_used_kwh": row["kwh"]})
        return trend

    future_usage = sum(row["kwh"] for row in usage_records)
    for row in usage_records:
        future_usage -= row["kwh"]
        trend.append(
            {
                "date": row["date"],
                "daily_used_kwh": row["kwh"],
                "estimated_remaining": round(remaining + future_usage, 2),
            }
        )
    return trend


def _last_unit_price(usage_records: list[dict[str, Any]]) -> float | None:
    for row in reversed(usage_records):
        if row["unit_price"] > 0:
            return row["unit_price"]
    return None


def _status_level(remaining: float | None, threshold: float | None) -> str:
    if remaining is None:
        return "unknown"
    if remaining <= 10:
        return "critical"
    if threshold is not None and remaining <= threshold:
        return "low"
    return "ok"


def _date_sort_key(value: str) -> datetime:
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return datetime.min


def _to_float(value: Any, default: float | None = 0.0) -> float | None:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return default


def _clean_text(value: str) -> str:
    return " ".join(html.unescape(value).split())


def _response_charset(content_type: str) -> str:
    match = re.search(r"charset=([\w-]+)", content_type, flags=re.IGNORECASE)
    if match:
        return match.group(1)
    return "gb2312"


def _normalize_base_url(url: str) -> str:
    return url.rstrip("/") + "/"
