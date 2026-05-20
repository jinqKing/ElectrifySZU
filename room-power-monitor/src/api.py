# 宿舍不断电 — API 客户端
# 对接 selectList.do 接口

import os
import tempfile
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
from typing import Optional, List, Dict

from .config import Config


class DormApi:
    """宿舍电费查询 API 客户端"""

    def __init__(self, config: Config):
        self.base_url = config.base_url.rstrip("/")
        self.client = config.client
        self.timeout = 10

    def _build_url(self, type_id: int, room_id: str, room_name: str,
                   begin: str, end: str) -> str:
        params = urllib.parse.urlencode({
            "type": type_id,
            "beginTime": begin,
            "endTime": end,
            "client": self.client,
            "roomId": room_id,
            "roomName": room_name,
        })
        return f"{self.base_url}/selectList.do?{params}"

    def _fetch(self, url: str) -> bytes:
        req = urllib.request.Request(url)
        proxy = os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy")
        if proxy:
            handler = urllib.request.ProxyHandler({"http": proxy, "https": proxy})
            opener = urllib.request.build_opener(handler)
            resp = opener.open(req, timeout=self.timeout)
        else:
            resp = urllib.request.urlopen(req, timeout=self.timeout)
        return resp.read()

    def get_recharge(self, room_id: str, room_name: str,
                     begin: str = "", end: str = "") -> bytes:
        """充值记录 (type=3) — 返回 Excel 二进制"""
        if not begin:
            begin = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        if not end:
            end = datetime.now().strftime("%Y-%m-%d")
        return self._fetch(self._build_url(3, room_id, room_name, begin, end))

    def get_usage(self, room_id: str, room_name: str,
                  begin: str = "", end: str = "",
                  as_excel: bool = True) -> bytes:
        """用电记录 (type=5 Excel / type=7 HTML)"""
        if not begin:
            begin = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        if not end:
            end = datetime.now().strftime("%Y-%m-%d")
        return self._fetch(
            self._build_url(5 if as_excel else 7, room_id, room_name, begin, end))

    def get_status(self, room_id: str, room_name: str) -> Dict:
        """获取房间用电摘要"""
        usage_data = self.get_usage(room_id, room_name,
                                    begin="2026-05-01", end="2026-05-20")
        usage = parse_excel(usage_data)

        recharge_data = self.get_recharge(room_id, room_name)
        recharge = parse_excel(recharge_data)

        result = {"room_name": room_name, "records": len(usage)}

        if usage:
            last = usage[-1]
            first = usage[0]
            keys = list(first.keys())
            result["remaining"] = float(last[keys[2]])
            total_used = float(last[keys[3]]) - float(first[keys[3]])
            result["total_used_kwh"] = round(total_used, 2)
            result["daily_avg_kwh"] = round(total_used / len(usage), 2)
            result["est_days_left"] = round(
                result["remaining"] / result["daily_avg_kwh"], 1)
            result["last_record"] = last[keys[5]]

        if recharge:
            recs = []
            for r in recharge:
                rkeys = list(r.keys())
                recs.append({
                    "time": r[rkeys[6]],
                    "kwh": float(r[rkeys[4]]),
                    "yuan": float(r[rkeys[5]]),
                    "method": r[rkeys[3]],
                })
            result["recharges"] = recs

        return result


def parse_excel(data: bytes) -> List[Dict]:
    """解析 Excel 为字典列表"""
    import xlrd
    tmp = tempfile.NamedTemporaryFile(suffix=".xls", delete=False)
    tmp.write(data)
    tmp.close()
    try:
        wb = xlrd.open_workbook(tmp.name)
        sheet = wb.sheets()[0]
        headers = [sheet.cell_value(0, c) for c in range(sheet.ncols)]
        return [{
            headers[c]: sheet.cell_value(r, c) for c in range(sheet.ncols)
        } for r in range(1, sheet.nrows)]
    finally:
        os.unlink(tmp.name)
