from __future__ import annotations

import argparse
import json
import mimetypes
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent
MONITOR_DIR = ROOT / "room-power-monitor"
WEB_DIR = ROOT / "web"
sys.path.insert(0, str(MONITOR_DIR))

from src.api import DormApi  # noqa: E402
from src.config import Config  # noqa: E402


class DashboardHandler(BaseHTTPRequestHandler):
    server_version = "ElectrifySZU/0.1"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/status":
            self._handle_status(parse_qs(parsed.query))
            return
        if parsed.path == "/api/demo-status":
            self._send_json(demo_status())
            return
        self._serve_static(parsed.path)

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"{self.address_string()} - {fmt % args}")

    def _handle_status(self, query: dict[str, list[str]]) -> None:
        try:
            config = Config.from_env(str(MONITOR_DIR / ".env"))
            api = DormApi(config)
            room_id = _query_value(query, "roomId") or config.room_id
            room_name = _query_value(query, "roomName") or config.room_name
            days = int(_query_value(query, "days") or "30")
            result = api.get_status(
                room_id=room_id,
                room_name=room_name,
                days=days,
                threshold=config.low_power_threshold,
            )
            self._send_json({"ok": True, "data": result})
        except Exception as exc:
            self._send_json(
                {
                    "ok": False,
                    "error": str(exc),
                    "hint": "请确认已连接校园网，并正确填写 room-power-monitor/.env。",
                },
                status=502,
            )

    def _serve_static(self, path: str) -> None:
        if path in {"", "/"}:
            path = "/index.html"
        target = (WEB_DIR / path.lstrip("/")).resolve()
        if not str(target).startswith(str(WEB_DIR.resolve())) or not target.is_file():
            self.send_error(404)
            return

        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        data = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, payload: dict[str, object], status: int = 200) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def _query_value(query: dict[str, list[str]], key: str) -> str:
    values = query.get(key, [])
    return values[0].strip() if values else ""


def demo_status() -> dict[str, object]:
    return {
        "ok": True,
        "data": {
            "room_id": "7322",
            "room_name": "713",
            "period": {"begin": "2026-04-20", "end": "2026-05-20", "days": 30},
            "records": 30,
            "threshold_kwh": 20,
            "status": "low",
            "remaining": 18.6,
            "total_used_kwh": 42.8,
            "daily_avg_kwh": 1.43,
            "est_days_left": 13.0,
            "last_record": "2026-05-20",
            "recharges": [
                {"time": "2026-05-08", "kwh": 50, "yuan": 30.5, "method": "微信支付"},
                {"time": "2026-04-19", "kwh": 30, "yuan": 18.3, "method": "支付宝"},
            ],
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the ElectrifySZU dashboard.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8000, type=int)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), DashboardHandler)
    print(f"ElectrifySZU dashboard: http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
