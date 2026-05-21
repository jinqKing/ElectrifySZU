from __future__ import annotations

import argparse
import json
import mimetypes
import re
import sys
from email import policy
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

ROOT = Path(__file__).resolve().parent
MONITOR_DIR = ROOT / "room-power-monitor"
WEB_DIR = ROOT / "web"
BUILDINGS_FILE = MONITOR_DIR / "data" / "buildings.txt"
ENV_FILE = ROOT / ".env"
sys.path.insert(0, str(MONITOR_DIR))

from src.api import DormApi  # noqa: E402
from src.config import Config  # noqa: E402
from src.discover import discover_room_id  # noqa: E402
from src.version import __version__  # noqa: E402
from subscription_alerts.alerts import AlertRunner, AlertSettings, start_alert_worker  # noqa: E402
from subscription_alerts.store import SubscriptionStore  # noqa: E402
from subscription_alerts.unsubscribe import unsubscribe_subscription  # noqa: E402
from subscription_alerts.verification import (  # noqa: E402
    create_pending_subscription,
    verify_subscription,
)


class DashboardHandler(BaseHTTPRequestHandler):
    server_version = f"ElectrifySZU/{__version__}"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        if parsed.path == "/api/status":
            self._handle_status(query)
            return
        if parsed.path == "/api/buildings":
            self._handle_buildings()
            return
        if parsed.path == "/api/demo-status":
            self._send_json(demo_status())
            return
        if parsed.path == "/api/unsubscribe":
            self._handle_unsubscribe(query)
            return
        if parsed.path == "/api/subscriptions/verify":
            self._handle_verify_subscription(query)
            return
        if parsed.path == "/api/alerts/check":
            self._handle_alert_check(query)
            return
        self._serve_static(parsed.path)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/subscriptions":
            self._handle_subscription()
            return
        self._send_json({"ok": False, "error": "Not found"}, status=404)

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"{self.address_string()} - {fmt % args}")

    def _handle_status(self, query: dict[str, list[str]]) -> None:
        try:
            config = Config.from_env(str(ENV_FILE))
            client = _query_value(query, "client") or config.client
            campus_name = _query_value(query, "campusName") or config.campus_name
            building_id = _query_value(query, "buildingId") or config.building_id
            building_name = _query_value(query, "buildingName") or config.building_name
            room_name = _query_value(query, "roomName") or config.room_name
            days = int(_query_value(query, "days") or "30")

            config.client = client
            room_id = discover_room_id(
                building_id=building_id,
                room_name=room_name,
                client_ip=client,
            )
            if not room_id:
                raise LookupError(f"未找到 {campus_name} {building_name} {room_name} 房间。")

            result = DormApi(config).get_status(
                room_id=room_id,
                room_name=room_name,
                days=days,
                threshold=config.low_power_threshold,
            )
            result["client"] = client
            result["campus_name"] = campus_name
            result["building_id"] = building_id
            result["building_name"] = building_name
            self._send_json({"ok": True, "data": result})
        except Exception as exc:
            self._send_json(
                {
                    "ok": False,
                    "error": str(exc),
                    "hint": "请确认已连接校园网，并检查楼栋与房间号是否正确。",
                },
                status=502,
            )

    def _handle_buildings(self) -> None:
        config = Config.from_env(str(ENV_FILE))
        data = merge_campuses(default_campuses(config), load_buildings_file())
        self._send_json({"ok": True, "data": data})

    def _handle_subscription(self) -> None:
        try:
            config = Config.from_env(str(ENV_FILE))
            settings = AlertSettings.from_env(ROOT)
            store = SubscriptionStore(settings.csv_path)
            data = self._read_request_data()
            result = create_pending_subscription(
                store=store,
                values={
                    "email": data.get("email", ""),
                    "client": data.get("client", "") or config.client,
                    "campus_name": data.get("campusName", "") or config.campus_name,
                    "building_id": data.get("buildingId", "") or config.building_id,
                    "building_name": data.get("buildingName", "") or config.building_name,
                    "room_name": data.get("roomName", "") or config.room_name,
                    "threshold_kwh": data.get(
                        "thresholdKwh",
                        str(config.low_power_threshold),
                    ),
                },
                default_threshold=config.low_power_threshold,
                base_url=settings.base_url,
                env_path=settings.env_path,
                request_base_url=self._request_base_url(),
            )
            subscription = result.subscription

            self._send_json(
                {
                    "ok": True,
                    "data": {
                        "email": subscription.email,
                        "campus_name": subscription.campus_name,
                        "building_name": subscription.building_name,
                        "room_name": subscription.room_name,
                        "threshold_kwh": subscription.threshold_kwh,
                        "verified": subscription.verified,
                    },
                    "message": (
                        "验证邮件已发送，请点击邮件中的确认链接后启用低电量预警。"
                        if result.verification_required
                        else "该邮箱订阅已生效，后续低电量会按规则发送提醒。"
                    ),
                    "verification_required": result.verification_required,
                },
                status=201,
            )
        except ValueError as exc:
            self._send_json({"ok": False, "error": str(exc)}, status=400)
        except Exception as exc:
            self._send_json(
                {
                    "ok": False,
                    "error": str(exc),
                    "hint": "订阅保存失败，请稍后重试或联系管理员。",
                },
                status=500,
            )

    def _handle_verify_subscription(self, query: dict[str, list[str]]) -> None:
        settings = AlertSettings.from_env(ROOT)
        token = _query_value(query, "token")
        status, subscription = verify_subscription(SubscriptionStore(settings.csv_path), token)
        if status == "verified" and subscription is not None:
            self._redirect_to_dashboard(
                {
                    "notice": "verified",
                    "email": subscription.email,
                    "campus": subscription.campus_name,
                    "building": subscription.building_name,
                    "room": subscription.room_name,
                }
            )
            return
        if status == "already_verified" and subscription is not None:
            self._redirect_to_dashboard(
                {
                    "notice": "already_verified",
                    "email": subscription.email,
                    "campus": subscription.campus_name,
                    "building": subscription.building_name,
                    "room": subscription.room_name,
                }
            )
            return
        self._redirect_to_dashboard({"notice": "verify_invalid"})

    def _handle_unsubscribe(self, query: dict[str, list[str]]) -> None:
        settings = AlertSettings.from_env(ROOT)
        token = _query_value(query, "token")
        status, subscription = unsubscribe_subscription(SubscriptionStore(settings.csv_path), token)
        if status == "unsubscribed" and subscription is not None:
            self._redirect_to_dashboard(
                {
                    "notice": "unsubscribed",
                    "email": subscription.email,
                    "campus": subscription.campus_name,
                    "building": subscription.building_name,
                    "room": subscription.room_name,
                }
            )
            return
        if status == "already_unsubscribed" and subscription is not None:
            self._redirect_to_dashboard(
                {
                    "notice": "already_unsubscribed",
                    "email": subscription.email,
                    "campus": subscription.campus_name,
                    "building": subscription.building_name,
                    "room": subscription.room_name,
                }
            )
            return
        self._redirect_to_dashboard({"notice": "unsubscribe_invalid"})

    def _handle_alert_check(self, query: dict[str, list[str]]) -> None:
        skip_recent = _query_value(query, "skipRecent").lower() not in {"0", "false", "no"}
        stats = AlertRunner(ROOT).run_once(skip_recent=skip_recent)
        self._send_json({"ok": True, "data": stats})

    def _serve_static(self, path: str) -> None:
        if path in {"", "/"}:
            path = "/index.html"
        base_dir = WEB_DIR.resolve()
        target = (base_dir / path.lstrip("/")).resolve()
        try:
            target.relative_to(base_dir)
        except ValueError:
            self.send_error(404)
            return

        if not target.is_file():
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

    def _send_plain(self, text: str, status: int = 200) -> None:
        data = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _read_request_data(self) -> dict[str, str]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(length)
        content_type = self.headers.get("Content-Type", "")
        if "application/json" in content_type:
            payload = json.loads(body.decode("utf-8") or "{}")
            return {str(key): str(value).strip() for key, value in payload.items()}
        if "multipart/form-data" in content_type:
            headers = f"Content-Type: {content_type}\n\n".encode("utf-8")
            message = BytesParser(policy=policy.default).parsebytes(headers + body)
            return {
                str(part.get_param("name", header="content-disposition")): part.get_payload(
                    decode=True
                ).decode(part.get_content_charset("utf-8")).strip()
                for part in message.iter_parts()
                if part.get_param("name", header="content-disposition")
            }
        parsed = parse_qs(body.decode("utf-8"), keep_blank_values=True)
        return {key: values[0].strip() if values else "" for key, values in parsed.items()}

    def _request_base_url(self) -> str:
        host = self.headers.get("Host", "127.0.0.1:8000").strip() or "127.0.0.1:8000"
        scheme = "https" if self.headers.get("X-Forwarded-Proto", "").lower() == "https" else "http"
        return f"{scheme}://{host}"

    def _redirect_to_dashboard(self, params: dict[str, str]) -> None:
        location = f"/?{urlencode(params)}"
        self.send_response(302)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.end_headers()


def _query_value(query: dict[str, list[str]], key: str) -> str:
    values = query.get(key, [])
    return values[0].strip() if values else ""


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
            current["buildings"].append(
                {
                    "id": building_match.group(1),
                    "name": building_match.group(2).strip(),
                }
            )
    return campuses


def default_campuses(config: Config) -> list[dict[str, object]]:
    return [
        {
            "client": config.client,
            "name": config.campus_name,
            "buildings": [{"id": config.building_id, "name": config.building_name}],
        }
    ]


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


def demo_status() -> dict[str, object]:
    return {
        "ok": True,
        "data": {
            "building_id": "7126",
            "client": "192.168.84.87",
            "campus_name": "粤海",
            "building_name": "风槐斋",
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
            "trend": [
                {"date": "2026-05-14", "remaining": 27.8, "daily_used_kwh": 1.5},
                {"date": "2026-05-15", "remaining": 26.1, "daily_used_kwh": 1.7},
                {"date": "2026-05-16", "remaining": 24.9, "daily_used_kwh": 1.2},
                {"date": "2026-05-17", "remaining": 23.0, "daily_used_kwh": 1.9},
                {"date": "2026-05-18", "remaining": 21.4, "daily_used_kwh": 1.6},
                {"date": "2026-05-19", "remaining": 20.0, "daily_used_kwh": 1.4},
                {"date": "2026-05-20", "remaining": 18.6, "daily_used_kwh": 1.4},
            ],
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
    parser.add_argument(
        "--check-now",
        action="store_true",
        help="Run one alert check immediately before serving.",
    )
    parser.add_argument(
        "--no-skip",
        action="store_true",
        help="Do not skip subscriptions already alerted today.",
    )
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), DashboardHandler)
    print(f"ElectrifySZU dashboard: http://{args.host}:{args.port}")
    if args.check_now:
        stats = AlertRunner(ROOT).run_once(skip_recent=not args.no_skip)
        print(f"[alert] startup check finished: {stats}")
    start_alert_worker(ROOT, skip_recent=not args.no_skip)
    server.serve_forever()


if __name__ == "__main__":
    main()
